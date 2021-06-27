using Torch.Commands;
using Torch.Commands.Permissions;
using VRage.Game.ModAPI;

namespace Hosting
{
    [Category("hosting")]
    public class HostingCommands : CommandModule
    {
        [Command("info", "Prints the current settings")]
        [Permission(MyPromoteLevel.None)]
        public void Info()
        {
            if (!HostingConfig.Instance.Enabled)
            {
                Context.Respond("Hosting plugin is disabled");
                return;
            }

            var identityId = Context.Player.IdentityId;
            if (identityId == 0L)
            {
                Context.Respond("This command can only be used in game");
                return;
            }

            RespondWithInfo();
        }

        [Command("enable", "Enables the plugin")]
        [Permission(MyPromoteLevel.Admin)]
        public void BlockLimit(bool enable)
        {
            HostingConfig.Instance.Enabled = true;
            HostingConfig.Instance.Save();
            RespondWithInfo();
        }

        [Command("disable", "Disables the plugin")]
        [Permission(MyPromoteLevel.Admin)]
        public void PcuLimit(bool enable)
        {
            HostingConfig.Instance.Enabled = false;
            HostingConfig.Instance.Save();
            RespondWithInfo();
        }

        private void RespondWithInfo()
        {
            var config = HostingConfig.Instance;
            Context.Respond("Hosting:\r\n" +
                            $"Enabled: {FormatBool(config.Enabled)}\r\n");
        }

        private static string FormatBool(bool value)
        {
            return value ? "Yes" : "No";
        }
    }
}