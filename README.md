# Steam Library Tracker

A lightweight desktop app for organising, tracking and exploring your Steam library.

Steam Library Tracker runs locally on your computer and uses the Steam Web API to load your games and playtime. Personal statuses, notes and cached metadata are stored locally.

## Features

- Import your Steam library and playtime
- Organise games by status:
  - Never played
  - Backlog
  - Playing
  - Finished
- Add personal notes to games
- Browse and filter your library
- Use **Smart Pick** when you do not know what to play
- Fetch and cache Steam Store metadata
- Local persistent storage
- Single-instance launcher with automatic recovery
- Update notifications through GitHub Releases
- Standalone builds for Windows and Linux

## Download

Pre-built versions are distributed through the GitHub **Releases** page.

### Windows

1. Download the Windows `.zip` release.
2. Extract the archive.
3. Run:

```text
SteamLibraryTracker.exe
```

No Python installation is required.

### Linux

1. Download the Linux `.tar.xz` release.
2. Extract it:

```bash
tar -xf SteamLibraryTracker-v1.0.0-linux-x86_64.tar.xz
```

3. Enter the extracted directory and run:

```bash
./SteamLibraryTracker
```

If execution permission is missing:

```bash
chmod +x SteamLibraryTracker
./SteamLibraryTracker
```

No Python installation is required.

## First launch

On first launch, Steam Library Tracker asks for the information required to access your Steam library.

You will need:

- a Steam Web API key
- your SteamID64

## Local data

Steam Library Tracker stores user data outside the application folder so updates do not overwrite your settings, statuses or notes.

### Linux

```text
~/.local/share/SteamLibraryTracker/
```

### Windows

```text
%LOCALAPPDATA%\SteamLibraryTracker\
```

This folder contains files such as:

```text
config.json
library.db
```

## Updates

Steam Library Tracker can check GitHub Releases for newer versions.

When a newer version is available, the app displays an update notification with a link to the corresponding release.

## Privacy

Steam Library Tracker is a local desktop application.

Personal notes, statuses, configuration and cached library data remain on your computer unless you explicitly export or share them.

## Development

For instructions on running or building Steam Library Tracker from source, see [BUILDING.md](BUILDING.md).

## Disclaimer

Steam Library Tracker is an independent project and is not affiliated with or endorsed by Valve Corporation.

Steam and the Steam logo are trademarks and/or registered trademarks of Valve Corporation.
