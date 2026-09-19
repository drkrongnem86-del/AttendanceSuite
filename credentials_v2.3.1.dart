// Credentials v2.3.1 - Tất cả sensitive credentials được mã hóa XOR
//
// ⚠️ Bảo mật: XOR với key cố định KHÔNG phải secure encryption - chỉ đủ để:
//   1. Không ai grep code thấy plaintext
//   2. Không hiện trong string extraction từ APK
//   3. Nếu ai đó xem được source code, phải decode mới biết
//
// Pattern copied từ HIS Mobile v3.0.96 - đổi key để rotate nếu lộ.
//
// Khi cần dùng: `import 'package:attendance_mobile/core/security/credentials.dart';`
//                `final pass = Credentials.vpnNemkPassword;`

import 'dart:convert';

class Credentials {
  // Key XOR (đổi key này để rotate - chỉ cần đổi 1 dòng)
  static const String _xorKey = 'BV_ATTENDANCE_2026_XOR_V231';

  /// Decode XOR-encoded string
  static String _decode(String encodedB64) {
    try {
      final xored = base64.decode(encodedB64);
      final key = utf8.encode(_xorKey);
      final bytes = List<int>.generate(
        xored.length,
        (i) => xored[i] ^ key[i % key.length],
      );
      return utf8.decode(bytes);
    } catch (_) {
      return '';
    }
  }

  /// Encode plain string (helper - chỉ dùng lúc dev, không gọi runtime)
  static String encode(String plain) {
    final bytes = utf8.encode(plain);
    final key = utf8.encode(_xorKey);
    final xored = List<int>.generate(
      bytes.length,
      (i) => bytes[i] ^ key[i % key.length],
    );
    return base64.encode(xored);
  }

  // ============ VPN (openvpn_flutter) ============
  /// OpenVPN password cho account mặc định (BS Ninh Thuận)
  /// XOR-encoded - dùng Credentials.encode('Cnttbvnt@321') để regenerate nếu cần rotate
  static final String vpnNemkPassword = _decode('ATgrNTYiKzoEcnxy');
}
