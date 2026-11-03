// Capri.exe - the one file you run. Capri herself is packed inside it (an embedded zip of her app folder).
//
// The first time a version runs, it unpacks her once into %LOCALAPPDATA%\Capri\app\<version>\ (a small window
// shows the progress), then starts her from there. Every start after that is instant. Old versions are cleaned
// up. When Capri updates, she replaces this same Capri.exe with the new one, so it stays the same app: same file,
// same place, same taskbar pin, same "start with Windows".
//
// Built by the release workflow with the C# compiler that comes with Windows (.NET Framework 4.x).

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Capri")]
[assembly: AssemblyProduct("Capri")]
[assembly: AssemblyDescription("Capri - a cyberpunk desktop companion")]

static class CapriLauncher
{
    static string Version()
    {
        using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("version.txt"))
        using (var r = new StreamReader(s, Encoding.UTF8))
            return r.ReadToEnd().Trim();
    }

    static string Quote(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return a;
        return "\"" + a.Replace("\\\"", "\\\\\"").Replace("\"", "\\\"") + "\"";
    }

    [STAThread]
    static int Main(string[] args)
    {
        string version = Version();
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Capri", "app");
        string dir = Path.Combine(root, version);
        string core = Path.Combine(dir, "Capri", "Capri.exe");
        bool extractOnly = Array.IndexOf(args, "--extract-only") >= 0;
        if (!File.Exists(Path.Combine(dir, ".ready")) || !File.Exists(core))
        {
            string problem = Unpack(dir, version, !extractOnly);
            if (problem != null)
            {
                if (!extractOnly)
                    MessageBox.Show("Capri couldn't unpack herself:\n\n" + problem, "Capri", MessageBoxButtons.OK,
                                    MessageBoxIcon.Error);
                else
                    Console.Error.WriteLine(problem);
                return 1;
            }
        }
        CleanUp(root, version);
        if (extractOnly) return 0;
        var info = new ProcessStartInfo(core);
        var line = new StringBuilder();
        foreach (var a in args) line.Append(Quote(a)).Append(' ');
        info.Arguments = line.ToString().Trim();
        info.UseShellExecute = false;
        info.WorkingDirectory = Path.GetDirectoryName(core);
        info.EnvironmentVariables["CAPRI_PORTABLE"] = Assembly.GetExecutingAssembly().Location;   // updates replace this
        try { Process.Start(info); }
        catch (Exception e)
        {
            MessageBox.Show("Capri couldn't start:\n\n" + e.Message, "Capri", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }

    // -- unpacking (once per version) -------------------------------------------------------------------------------
    static string Unpack(string dir, string version, bool window)
    {
        string tmp = dir + ".unpacking";
        string problem = null;
        Form form = null;
        ProgressBar bar = null;
        if (window)
        {
            form = new Form();
            form.Text = "Capri";
            form.FormBorderStyle = FormBorderStyle.FixedSingle;
            form.MaximizeBox = form.MinimizeBox = false;
            form.StartPosition = FormStartPosition.CenterScreen;
            form.ClientSize = new Size(380, 96);
            form.BackColor = Color.FromArgb(10, 8, 14);
            form.Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
            var label = new Label();
            label.Text = "Setting up Capri " + version + " (only the first time)...";
            label.ForeColor = Color.FromArgb(255, 60, 100);
            label.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            label.SetBounds(18, 18, 344, 24);
            bar = new ProgressBar();
            bar.SetBounds(18, 54, 344, 18);
            bar.Maximum = 1000;
            form.Controls.Add(label);
            form.Controls.Add(bar);
        }
        var work = new Thread(() =>
        {
            try
            {
                if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                Directory.CreateDirectory(tmp);
                using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("capri.zip"))
                using (var zip = new ZipArchive(s, ZipArchiveMode.Read))
                {
                    int total = zip.Entries.Count, done = 0;
                    string full = Path.GetFullPath(tmp) + Path.DirectorySeparatorChar;
                    foreach (var entry in zip.Entries)
                    {
                        string target = Path.GetFullPath(Path.Combine(tmp, entry.FullName));
                        if (!target.StartsWith(full, StringComparison.OrdinalIgnoreCase)) continue;   // stays inside
                        if (entry.FullName.EndsWith("/")) Directory.CreateDirectory(target);
                        else
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(target));
                            entry.ExtractToFile(target, true);
                        }
                        done++;
                        if (bar != null && done % 20 == 0)
                        {
                            int value = (int)(1000L * done / Math.Max(1, total));
                            bar.BeginInvoke((Action)(() => bar.Value = Math.Min(1000, value)));
                        }
                    }
                }
                Directory.Move(tmp, dir);
                File.WriteAllText(Path.Combine(dir, ".ready"), version);
            }
            catch (Exception e)
            {
                problem = e.Message;
                try { if (Directory.Exists(tmp)) Directory.Delete(tmp, true); } catch { }
            }
            if (form != null) form.BeginInvoke((Action)(() => form.Close()));
        });
        work.IsBackground = true;
        work.Start();
        if (form != null) Application.Run(form);
        work.Join();
        return problem;
    }

    static void CleanUp(string root, string keep)
    {
        try
        {
            foreach (var d in Directory.GetDirectories(root))
            {
                if (string.Equals(Path.GetFileName(d), keep, StringComparison.OrdinalIgnoreCase)) continue;
                string exe = Path.Combine(d, "Capri", "Capri.exe");
                if (File.Exists(exe))
                {
                    try { using (File.Open(exe, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } }
                    catch { continue; }                                // that Capri is still running: next time then
                }
                try { Directory.Delete(d, true); } catch { }
            }
        }
        catch { }
    }
}
