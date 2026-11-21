// StoryCore.exe: starts the bundled Python with scripts\serve.py, in this console window.
// Compiled by scripts\release\publish.ps1 with the C# compiler that ships with Windows (.NET Framework 4),
// so it uses C# 5 only (no string interpolation, no "?.").
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

[assembly: System.Reflection.AssemblyTitle("StoryCore")]
[assembly: System.Reflection.AssemblyProduct("StoryCore")]

static class Launcher
{
    static string Quote(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return a;
        var sb = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in a)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { sb.Append('\\', slashes * 2 + 1); sb.Append('"'); }
            else { sb.Append('\\', slashes); sb.Append(c); }
            slashes = 0;
        }
        sb.Append('\\', slashes * 2);
        sb.Append('"');
        return sb.ToString();
    }

    static void Pause()
    {
        Console.WriteLine();
        Console.WriteLine("  Press a key to close this window.");
        try { Console.ReadKey(true); } catch (InvalidOperationException) { }
    }

    static int Main(string[] args)
    {
        // Velopack starts the app with --veloapp-... during install, update and uninstall: never wait for a key then.
        bool hook = args.Length > 0 && args[0].StartsWith("--veloapp-", StringComparison.OrdinalIgnoreCase);
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string python = Path.Combine(root, @"app\python\python.exe");
        string serve = Path.Combine(root, @"scripts\serve.py");
        try { Console.Title = "StoryCore"; } catch (IOException) { }

        if (!File.Exists(python) || !File.Exists(serve))
        {
            Console.WriteLine();
            Console.WriteLine("  StoryCore cannot find its files in " + root);
            Console.WriteLine("  Please reinstall StoryCore.");
            if (!hook) Pause();
            return 1;
        }

        var cmd = new StringBuilder("--check-hash-based-pycs always ");
        cmd.Append(Quote(serve));
        foreach (string a in args) { cmd.Append(' '); cmd.Append(Quote(a)); }

        var psi = new ProcessStartInfo(python, cmd.ToString());
        psi.UseShellExecute = false;
        psi.WorkingDirectory = root;
        // The app uses its own bundled Python: ignore any Python settings from this computer.
        psi.EnvironmentVariables.Remove("PYTHONHOME");
        psi.EnvironmentVariables.Remove("PYTHONPATH");
        psi.EnvironmentVariables.Remove("PYTHONSTARTUP");
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";
        psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";

        if (!hook)
        {
            Console.WriteLine();
            Console.WriteLine("  Starting StoryCore. Your browser will open by itself.");
            Console.WriteLine("  The first start can take up to a minute. Keep this window open while you play.");
            Console.WriteLine();
        }

        int code;
        try
        {
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit();
                code = p.ExitCode;
            }
        }
        catch (Exception e)
        {
            Console.WriteLine("  StoryCore could not start: " + e.Message);
            if (!hook) Pause();
            return 1;
        }

        if (code != 0 && !hook)
        {
            Console.WriteLine();
            Console.WriteLine("  StoryCore stopped with an error. See the messages above.");
            Pause();
        }
        return code;
    }
}
