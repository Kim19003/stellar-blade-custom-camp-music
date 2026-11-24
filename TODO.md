# TODO

- [ ] **Clean up existing camp music mod files when writing a new build**
  - Stellar Blade only loads a single override of `TurntableSoundTable.uasset` and `StringTable_UI.uasset`, so multiple custom camp music mods cannot be active simultaneously in `~mods` (whichever mounts last shadows the others—for example, having both `CampMusic_Custom_295_P.{pak,utoc,ucas}` and `CampMusic_Radio_295_P.{pak,utoc,ucas}`).
  - When installing/writing a new mod (via CLI or either GUI), remove (or prompt/opt-in to remove) existing camp music mod `.pak`, `.utoc`, and `.ucas` files in the target output/`~mods` directory—especially older `CampMusic_*` packages or any containers overriding `TurntableSoundTable`—before writing the new mod files.
