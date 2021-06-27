using System.Diagnostics;
using System.IO;
using NLog;
using Torch;
using Torch.API;
using Torch.API.Managers;
using Torch.API.Session;
using Torch.Session;

namespace Hosting
{
    // ReSharper disable once ClassNeverInstantiated.Global
    public class HostingPlugin : TorchPluginBase
    {
        private const string PluginName = "Hosting";

        private static Logger log;
        private static Logger Log => log ?? (log = LogManager.GetLogger(PluginName));

        public static HostingPlugin Instance { get; private set; }
        private TorchSessionManager sessionManager;
        private bool Initialized => sessionManager != null;

        // ReSharper disable once UnusedMember.Local
        private readonly HostingCommands commands = new HostingCommands();

        public static bool Loaded { get; private set; }
        private Canary canary;

        [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
        public override void Init(ITorchBase torch)
        {
            base.Init(torch);
            Instance = this;

            sessionManager = torch.Managers.GetManager<TorchSessionManager>();
            sessionManager.SessionStateChanged += SessionStateChanged;

            Log.Info($"Loaded {PluginName} plugin");
        }

        private void SessionStateChanged(ITorchSession session, TorchSessionState newState)
        {
            switch (newState)
            {
                case TorchSessionState.Loading:
                    break;
                case TorchSessionState.Loaded:
                    canary = new Canary(StoragePath);
                    WritePid();
                    Loaded = true;
                    break;
                case TorchSessionState.Unloading:
                    Loaded = false;
                    canary = null;
                    break;
                case TorchSessionState.Unloaded:
                    break;
            }
        }

        public override void Update()
        {
            if (!Loaded)
                return;

            if (!HostingConfig.Instance.Enabled)
                return;

            canary.Update();
        }

        public override void Dispose()
        {
            if (!Initialized)
                return;

            Log.Info($"Unloaded {PluginName} plugin");

            sessionManager.SessionStateChanged -= SessionStateChanged;
            sessionManager = null;

            Instance = null;

            base.Dispose();
        }

        public void WritePid()
        {
            var process = Process.GetCurrentProcess();
            var pidPath = Path.Combine(StoragePath, "pid");
            File.WriteAllText(pidPath, process.Id.ToString());
            Log.Info($"PID: {process.Id}");
        }
    }
}