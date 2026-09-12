// AttendanceSuite launcher - extracts embedded ZIP and runs run_all.bat
using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Threading;

class Launcher {
    [STAThread]
    static int Main(string[] args) {
        Console.WriteLine("AttendanceSuite v1.3.0 (build 4) - BVĐK Ninh Thuan");
        Console.WriteLine("Live Status + Reports + X628 PRO Simulator");
        Console.WriteLine("");
        string tempDir = Path.Combine(Path.GetTempPath(), "AttendanceSuite");
        string marker = Path.Combine(tempDir, ".installed");
        bool needExtract = !File.Exists(marker);
        
        try {
            if (needExtract) {
                // Clean up any previous partial install
                if (Directory.Exists(tempDir)) {
                    try { Directory.Delete(tempDir, true); } catch { }
                }
                Directory.CreateDirectory(tempDir);
                
                // Extract embedded ZIP from resources
                Assembly asm = Assembly.GetExecutingAssembly();
                using (Stream zipStream = asm.GetManifestResourceStream("Suite.Payload")) {
                    if (zipStream == null) {
                        Console.WriteLine("Error: Embedded payload not found");
                        return 1;
                    }
                    string tempZip = Path.Combine(Path.GetTempPath(), "AttendanceSuite_payload.zip");
                    using (FileStream fs = File.Create(tempZip)) {
                        zipStream.CopyTo(fs);
                    }
                    ZipFile.ExtractToDirectory(tempZip, tempDir);
                    try { File.Delete(tempZip); } catch { }
                }
                File.WriteAllText(marker, DateTime.Now.ToString());
            }
            
            // Launch run_all.bat
            string batPath = Path.Combine(tempDir, "run_all.bat");
            if (!File.Exists(batPath)) {
                Console.Error.WriteLine("Error: run_all.bat not found in extracted files");
                return 1;
            }
            
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "cmd.exe";
            psi.Arguments = "/c cd /d \"" + tempDir + "\" && run_all.bat";
            psi.UseShellExecute = true;
            psi.WorkingDirectory = tempDir;
            Process.Start(psi);
            return 0;
        } catch (Exception e) {
            Console.Error.WriteLine("Error: " + e.Message);
            return 1;
        }
    }
}
