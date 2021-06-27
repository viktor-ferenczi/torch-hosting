using System;
using System.IO;
using NLog;

namespace Hosting
{
    public class Canary
    {
        private static Logger log;
        private static Logger Log => log ?? (log = LogManager.GetLogger("Canary"));

        private const long WriteFrequency = 20 * 60;

        private readonly string path;
        private long ticks;

        public Canary(string storagePath)
        {
            path = Path.Combine(storagePath, "canary");
            Write();
        }

        public void Update()
        {
            if(ticks++ % WriteFrequency == 0)
                Write();
        }

        private void Write()
        {
            var now = DateTime.Now.ToString("o");
            File.WriteAllText(path, now);
            Log.Info(now);
        }
    }
}