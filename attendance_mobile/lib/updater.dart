// Auto-updater - check GitHub Releases API for newer versions
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class UpdateInfo {
  final String latestVersion;
  final String? downloadUrl;
  final String? releaseNotes;
  final bool isUpdateAvailable;

  UpdateInfo({
    required this.latestVersion,
    this.downloadUrl,
    this.releaseNotes,
    required this.isUpdateAvailable,
  });
}

class AppUpdater {
  // Repo cua BS Diem - doi thanh repo thuc te neu can
  static const String _repoOwner = 'drkrongnem86-del';
  static const String _repoName = 'AttendanceSuite';

  // Cache 24h de khong spam GitHub
  static DateTime? _lastCheck;
  static UpdateInfo? _cached;

  static String get currentVersion {
    // Hardcode vi Flutter khong the doc pubspec runtime de dang
    // Khi bump version can update o day
    return '1.3.3';
  }

  static Future<UpdateInfo> checkForUpdate({bool force = false}) async {
    // Neu cache con fresh va khong force, dung cache
    if (!force && _cached != null && _lastCheck != null) {
      final age = DateTime.now().difference(_lastCheck!);
      if (age.inHours < 24) return _cached!;
    }

    try {
      final url = Uri.parse(
        'https://api.github.com/repos/$_repoOwner/$_repoName/releases/latest',
      );
      final resp = await http.get(
        url,
        headers: {
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'AttendanceSuite-Mobile',
        },
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) {
        // Khong co release tag nao -> skip
        return UpdateInfo(
          latestVersion: currentVersion,
          isUpdateAvailable: false,
          releaseNotes: 'Khong the check update (status ${resp.statusCode})',
        );
      }

      final data = json.decode(resp.body) as Map<String, dynamic>;
      final tagName = (data['tag_name'] as String?) ?? '';
      final htmlUrl = data['html_url'] as String?;
      final body = (data['body'] as String?) ?? '';

      // Strip 'v' prefix
      final latestVer = tagName.startsWith('v')
          ? tagName.substring(1)
          : tagName;

      final hasUpdate = _compareVersions(latestVer, currentVersion) > 0;

      _cached = UpdateInfo(
        latestVersion: latestVer,
        downloadUrl: htmlUrl,
        releaseNotes: body.length > 500 ? body.substring(0, 500) + '...' : body,
        isUpdateAvailable: hasUpdate,
      );
      _lastCheck = DateTime.now();
      return _cached!;
    } catch (e) {
      return UpdateInfo(
        latestVersion: currentVersion,
        isUpdateAvailable: false,
        releaseNotes: 'Loi check update: $e',
      );
    }
  }

  // So sanh version: "1.3.3" > "1.3.2" -> 1; bang -> 0; nho hon -> -1
  static int _compareVersions(String a, String b) {
    try {
      final pa = a.split('.').map(int.parse).toList();
      final pb = b.split('.').map(int.parse).toList();
      final maxLen = pa.length > pb.length ? pa.length : pb.length;
      for (var i = 0; i < maxLen; i++) {
        final va = i < pa.length ? pa[i] : 0;
        final vb = i < pb.length ? pb[i] : 0;
        if (va > vb) return 1;
        if (va < vb) return -1;
      }
      return 0;
    } catch (e) {
      return 0;
    }
  }

  static Future<void> showUpdateDialog(BuildContext context, UpdateInfo info) async {
    if (!info.isUpdateAvailable) return;
    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.blueGrey.shade900,
        title: Row(
          children: [
            Icon(Icons.system_update, color: Colors.cyanAccent),
            const SizedBox(width: 8),
            const Text('Co phien ban moi', style: TextStyle(color: Colors.white)),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Phien ban hien tai: ${info.latestVersion}\n'
                'Phien ban moi: ${currentVersion}',
                style: const TextStyle(color: Colors.white, fontSize: 13),
              ),
              const SizedBox(height: 12),
              if (info.releaseNotes != null && info.releaseNotes!.isNotEmpty) ...[
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.black26,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    info.releaseNotes!,
                    style: const TextStyle(color: Colors.white70, fontSize: 11),
                  ),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('De sau', style: TextStyle(color: Colors.white60)),
          ),
          ElevatedButton.icon(
            icon: const Icon(Icons.download, size: 18),
            label: const Text('Tai ngay'),
            onPressed: () async {
              Navigator.of(ctx).pop();
              if (info.downloadUrl != null) {
                final uri = Uri.parse(info.downloadUrl!);
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.cyanAccent),
          ),
        ],
      ),
    );
  }
}
