using System;
using System.IO;
using System.Xml.Serialization;
using NLog;
using Torch;
using Torch.Views;

namespace Hosting
{
    [Serializable]
    public class HostingConfig : ViewModel
    {
        private static readonly Logger Log = LogManager.GetCurrentClassLogger();

        private static readonly string ConfigFileName = "Hosting.cfg";
        private static bool loading;

        private bool enabled = true;

        private static HostingConfig instance;
        public static HostingConfig Instance => instance ?? (instance = new HostingConfig());
        private static XmlSerializer ConfigSerializer => new XmlSerializer(typeof(HostingConfig));
        private static string ConfigFilePath => Path.Combine(HostingPlugin.Instance.StoragePath, ConfigFileName);

        [Display(Description = "Enables/disables the plugin", Name = "Enabled", Order = 1)]
        public bool Enabled
        {
            get => enabled;
            set
            {
                enabled = value;
                OnPropertyChanged(nameof(Enabled));
            }
        }

        protected override void OnPropertyChanged(string propName = "")
        {
            // FIXME: Frequent saving causes exception due to the file still being open. What?!
            //Save();
        }

        private void UnsafeSave()
        {
            using (var streamWriter = new StreamWriter(ConfigFilePath))
            {
                ConfigSerializer.Serialize(streamWriter, instance);
            }
        }

        private void UnsafeLoad(string path)
        {
            using (var streamReader = new StreamReader(path))
            {
                if (!(ConfigSerializer.Deserialize(streamReader) is HostingConfig config))
                {
                    Log.Error($"Failed to deserialize configuration file: {path}");
                    return;
                }

                instance = config;
            }
        }

        public void Save()
        {
            if (loading)
                return;

            lock (this)
            {
                try
                {
                    UnsafeSave();
                }
                catch (Exception e)
                {
                    Log.Error(e, $"Failed to save configuration file: {ConfigFilePath}");
                }
            }
        }

        public void Load()
        {
            loading = true;
            lock (this)
            {
                var path = ConfigFilePath;
                try
                {
                    if (!File.Exists(path))
                    {
                        Log.Warn($"Missing configuration file. Saving default one: {path}");
                        UnsafeSave();
                        return;
                    }

                    UnsafeLoad(path);
                }
                catch (Exception e)
                {
                    Log.Error(e, $"Failed to load configuration file: {path}");
                }
                finally
                {
                    loading = false;
                }
            }
        }
    }
}