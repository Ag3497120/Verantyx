export type CoreCliCommandDescriptor = {
  name: string;
  description: string;
  hasSubcommands: boolean;
};

export const CORE_CLI_COMMAND_DESCRIPTORS = [
  {
    name: "setup",
    description: "Initialize local config and agent workspace",
    hasSubcommands: false,
  },
  {
    name: "onboard",
    description: "Interactive onboarding for gateway, workspace, and skills",
    hasSubcommands: false,
  },
  {
    name: "configure",
    description: "Interactive configuration for credentials, channels, gateway, and agent defaults",
    hasSubcommands: false,
  },
  {
    name: "config",
    description:
      "Non-interactive config helpers (get/set/unset/file/validate). Default: starts guided setup.",
    hasSubcommands: true,
  },
  {
    name: "backup",
    description: "Create and verify local backup archives for Ronin Agent state",
    hasSubcommands: true,
  },
  {
    name: "doctor",
    description: "Health checks + quick fixes for the gateway and channels",
    hasSubcommands: false,
  },
  {
    name: "reset",
    description: "Reset local config/state (keeps the CLI installed)",
    hasSubcommands: false,
  },
  {
    name: "uninstall",
    description: "Uninstall the gateway service + local data (CLI remains)",
    hasSubcommands: false,
  },
] as const satisfies ReadonlyArray<CoreCliCommandDescriptor>;

export function getCoreCliCommandDescriptors(): ReadonlyArray<CoreCliCommandDescriptor> {
  return CORE_CLI_COMMAND_DESCRIPTORS;
}

export function getCoreCliCommandsWithSubcommands(): string[] {
  return CORE_CLI_COMMAND_DESCRIPTORS.filter((command) => command.hasSubcommands).map(
    (command) => command.name,
  );
}
