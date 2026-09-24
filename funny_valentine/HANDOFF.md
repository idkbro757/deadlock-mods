# Funny Valentine mod: handoff

For a Claude Code session running on the user's own Windows PC. Everything so far was done in a
cloud session that couldn't touch the PC, so the user had to click through every compile, pack
and install step by hand. They're tired of that. **Your main job is to do those steps yourself**
with the Valve command-line tools (see "Automating the pipeline"), then keep going with the
features below.

Repo: `idkbro757/deadlock-mods`, branch **`claude/brave-pasteur-17l5q5`** (everything is there;
`main` doesn't have it). Start by reading `funny_valentine/README.md` and this file.

## What the mod is

Funny Valentine (JoJo Part 7) replaces **Doorman** in Deadlock:

- His body is the Sketchfab model in `funny-valentine-d4c-sbr/`, fitted onto Doorman's skeleton by
  `funny_valentine/fv_build.py`. It's done and confirmed working in game, textures included.
- **His gun is his own revolver** (`props/fv_revolver.glb`, from the SFM pack) instead of the
  key-gun. Done, and the user saw it right way up in game.
- **D4C appears while someone is in Doorman's Hotel (the ult)** and floats next to the player.
  It works, but the position still needs tuning (see status).
- **Closed Doorway door = American flag.** Not started: it's waiting on Valve's door model.
- **Friends' download:** `.github/workflows/funny-valentine-release.yml` publishes whatever vpk is
  committed in `funny_valentine/release/` to
  https://github.com/idkbro757/deadlock-mods/releases/tag/funny-valentine. The zip includes
  `funny_valentine/share/Install Funny Valentine.bat`.

## Status and next steps, in order

1. **D4C position: build and test the committed offset.**
   - The last in-game test used `--offset -40,30,18`. D4C faced the right way and was behind the
     left shoulder, but the game camera is closer than expected: he was nearly on top of the
     camera, huge, and cut off at the left edge of the screen.
   - The committed `addon_files/` now has **`-15,32,12`**. It's untested.
   - The goal is the user's reference, the "Gappy (Josuke8) as Celeste" mod
     (https://gamebanana.com/mods/668377): the stand hovers beside and behind the hero on the
     left, fully in frame, not covering the crosshair.
   - To change it:
     `blender -b -P funny_valentine/d4c_prop.py -- --posed funny_valentine/props/d4c_posed.glb --addon <addon> --offset X,Y,Z`
     where X is back(-)/front, Y is right(-)/left, Z is up, relative to the player's feet in the
     player's facing frame. Then recompile the D4C model and the particle, and repack.
2. **Ship a good build to friends.**
   - The release currently has the **old broken D4C**: lying on his back next to the victim.
     That's commit `89def2f`, the last vpk the user uploaded.
   - Once D4C looks right, commit the new vpk to `funny_valentine/release/funny_valentine.vpk`
     and push. The Action publishes it.
3. **Flag door.**
   - Run `funny_valentine/tools/extract_door.ps1` on the PC. Nobody has to upload anything now.
     It uses the Source 2 Viewer CLI to pull `models/heroes_wip/doorman/doorman_door.vmdl_c`
     (decompiled + raw) and `particles/abilities/doorman/doorman_hotel_debuff.vpcf_c` out of
     `Deadlock\game\citadel\pak01_dir.vpk`.
   - The door vmdl has two render meshes. `doorman_doubledoor_portal` is the closed door panels,
     `doorman_frame` is the frame.
   - Bodygroup `default` has two choices: `door_on` (frame only = open) and `door_off`
     (panels + frame = closed).
   - Bones: `root`, `doorhinge_r`, `doorhinge_l` (hinges at y = +/-63.5). There's an animgraph
     `animgraphs/doorman_door.vanmgrph` and 4 physics hulls.
   - **Replace only the panel mesh with the flag.** Leave the frame, the open state, physics,
     animgraph and bodygroups alone.
   - Split the flag down the middle and weight each half to its hinge bone, assuming that's how
     Valve's panels are skinned (check).
   - Flag texture: `funny_valentine/flag_texture.py out.png 2048`. It's a sharp redraw of the SFM
     pack's 13-star Betsy Ross flag (the original `flag.vtf` is only 256px). The SFM flag mesh
     isn't in the repo; you don't need it for flat panels.
   - The model path `models/heroes_wip/doorman/doorman_door.vmdl` isn't in a hero folder, so the
     VMDL Compiler GUI won't list it. Compile it from the command line (below).
4. **Swap in Valve's current Hotel effect.**
   - `addon_files/particles/abilities/doorman/doorman_hotel_debuff.vpcf` overrides Valve's
     effect. It's Valve's structure plus one extra child (`particles/funny_valentine/d4c_hotel.vpcf`),
     but it was copied from the Gojo mod's copy (compiled 3562 bytes vs Valve's 3546 at the time).
   - The extractor above also pulls Valve's current one. Diff them, take Valve's, and re-add the
     D4C child entry.
5. Small things the user hasn't asked about:
   - Doorman's `doorman_keyglow` mesh (glowing keys on bones `key_a..d_0`, at the left hip) is
     still in every bodygroup, so it floats at FV's hip.
   - The revolver's muzzle ends about 3.5 units short of Doorman's `muzzle_fx` bone. The flash is
     slightly in front of the barrel.

## The user's PC

Seen in screenshots. **Verify before using.**

| thing | path |
|---|---|
| CSDK12 | `C:\Users\charl\Downloads\Reduced_CSDK_12\Reduced_CSDK_12` |
| the addon (source) | `...\Reduced_CSDK_12\content\citadel_addons\funny_valentine` |
| compiled output | `...\Reduced_CSDK_12\game\citadel_addons\funny_valentine` |
| CS2 (CSWin64) | `E:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive` (its `game\csgo_core\gameinfo.gi` already has the `content_consider_missing_materials_fatal` fix) |
| Deadlock | probably `E:\SteamLibrary\steamapps\common\Deadlock` (not confirmed) |
| installed mod | `Deadlock\game\citadel\addons\pak05_dir.vpk` (+ `funny_valentine.installed`, which holds that name) |

- `addons` also holds about 30 other mods named `NNNNNN_pakXX_dir.vpk`. Don't touch those.
- Blender install path: unknown. `build.bat` assumes `C:\Program Files\Blender Foundation\Blender 4.2`.
  It needs Blender Source Tools for DMX.
- Deadlock VMDL Compiler (kwlnd, GUI) exe: location unknown.

## Automating the pipeline

What the user has been clicking through, and the command-line version.

1. **Put files in the addon.** `tools/install_update.ps1` copies an `addon\` folder into the CSDK
   addon and stamps the times. Locally, just copy `funny_valentine/addon_files/*` plus the
   `fv_build.py` output into `...\content\citadel_addons\funny_valentine\`.
2. **Materials + particles ("Compile All Assets" in CSDK12).** Use CSDK12's
   `game\bin\win64\resourcecompiler.exe`.
   - Same pattern as below, probably `-f -i "<content file>" -game "<CSDK12>\game\citadel"`, with
     output landing in `game\citadel_addons\funny_valentine\`.
   - That's unverified: check `resourcecompiler.exe -h` and one file's output first.
3. **Models (the VMDL Compiler GUI).** It runs CS2's compiler, not CSDK12's. See
   https://github.com/kwlnd/deadlock-vmdl-compiler `Services/VmdlPipeline.cs`,
   `CompileViaCsWinAndDeployAsync`:
   1. Copy the vmdl's folder (`.dmx .vmat .png .vanim`) to `<CS2>\content\csgo_addons\funny_valentine\<same subpath>`.
   2. For **`doorman.vmdl` only**, inject the AG2 nodes before the `model_archetype` line:
      - an `NmSkeletonList` → `models/heroes_wip/doorman_v2/doorman.vnmskel`
      - an `AnimGraph2List` holding `DefaultAnimGraph2` →
        `animgraphs/animgraph2/hero/hero.vnmgraph+doorman.vnmgraph` and `AnimGraph2 name "ui"` →
        `animgraphs/animgraph2/hero/hero_ui.vnmgraph+doorman.vnmgraph`
      - Also set the header to modeldoc41.
      - The exact text is in `UpgradeVmdlContent`.
   3. Plain props (D4C, the flag door) need nothing injected.
   4. Run `<CS2>\game\bin\win64\resourcecompiler.exe -f -i "<CS2 vmdl path>" -game "<CS2>\game\csgo"`.
   5. Copy `<CS2>\game\csgo_addons\funny_valentine\<subpath>_c` to `<CSDK12>\game\citadel_addons\funny_valentine\<subpath>_c`.
4. **Pack ("make vpk...").** It's a single-file VPK v2 of `<CSDK12>\game\citadel_addons\funny_valentine\`,
   made by `Services/VpkBuilder.cs` (about 230 lines, easy to port).
5. **Install.** Copy it over `Deadlock\game\citadel\addons\pak05_dir.vpk`, then start the game.
   - Test with bots in the Sandbox.
   - Hotel a bot to see D4C. He only shows while it's checked in, about 6 seconds.
6. **Verify a vpk** before calling it done. The Source 2 Viewer CLI (`Source2Viewer-CLI.exe -i x.vpk -l`,
   and `-d -o dir` to decompile) should show:
   - `models/heroes_wip/doorman_v2/doorman.vmdl_c` (with `NmSkeletonList` / `AnimGraph2List`
     when decompiled)
   - `fv_d4c_hotel.vmdl_c`
   - the two `.vpcf_c`
   - `fv_body/fv_eyes/fv_revolver/fv_d4c` materials with their `_color_png_*.vtex_c`
   - The last good one was 6.2 MB.

## How D4C works, and the traps already hit

- **Lifecycle.** Valve puts `particles/abilities/doorman/doorman_hotel_debuff.vpcf` on the victim's
  stand-in (`modifier_doorman_hotel_imposter_fx`) for exactly as long as they're in the Hotel.
  - Our child effect copies Valve's floating key: one particle, lifetime 0.1, `C_OP_Decay` with
    `PARTICLE_ENDCAP_ENDCAP_ON`. So it lives until the game ends the effect.
  - The user explicitly asked for **no durations/timers**, because the stay length changes with
    items, early checkout, etc. Keep it that way.
- **Anchor.** The effect only knows the victim (CP0 = stand-in, CP1 = `ability_apply` attachment).
  Doorman has no effect or modifier of his own during the stay.
  - We use `C_OP_SetControlPointToPlayer` (local player, `m_bOrientToEyes`, `PARTICLE_ABS_ORIGIN`)
    on **CP 12** plus `C_OP_SetToCP` and `C_OP_RemapTransformOrientationToYaw`.
  - Side effect: a friend with the mod playing another hero sees D4C beside *themselves* while a
    victim's stand-in is nearby. The user has been told.
- **Upright.** The model renderer points the model's +X along the particle normal (straight up)
  unless `m_bIgnoreNormal = true`. Without it, D4C lay on his back.
- **Facing.** Deadlock draws effect models half a turn from the yaw given. Fixed with the
  renderer's `m_vecLocalRotation = [0, 180, 0]`, the same fix the Gappy mod's stand uses
  (`particles/abilities/unicorn/sawidle.vpcf` in its vpk).
- **Offset.** The offset is baked into the D4C mesh (`d4c_prop.py --offset`), not the effect,
  because eye orientation includes pitch.
  - Hover bob: renderer `m_vecLocalOffset` Z = collection-age curve, `PF_INPUT_MODE_LOOPED`,
    ±3 units over 3 s.
- **VMDL Compiler GUI quirks.**
  - It only lists models inside a hero folder, which is why D4C lives at
    `models/heroes_wip/doorman_v2/fv_d4c_hotel.vmdl`.
  - Its "browse..." picks a file outside the addon and then thinks the addon is named after the
    folder. The user hit this; always use the dropdown.
  - It rescans addons only at startup.
  - It rewrites `.vmdl` files after every compile.
- **CSDK12 "Compile All Assets"** must run *before* compiling `doorman.vmdl` in the VMDL Compiler.
  Otherwise a plain CSDK12 build could overwrite the AG2 one.

## Model-building facts (fv_build.py)

- Doorman is `models/heroes_wip/doorman_v2/doorman.vmdl`: 168 bones. Materials only read the
  **layer-1** inputs (`TextureColor1` etc.; `pbr.vfx`). Without the `1` suffix you get a white
  model.
- All parts need one UV map with the same name (`UVMap`) before joining, or BST exports
  all-zero UVs (another white model).
- CSWin64 copies a `.dmx` only if it's newer than its copy, so touch it after replacing it.
- Gun: `fit_gun()` puts the bore on the `barrel_a`→`muzzle_fx` line. The grip centre goes on the
  measured palm `1.1,0,1.0` in `weapon_offset` bind space. Barrel/top axes come from the bounding
  box or `--gun-forward/--gun-up` (the SFM revolver is -y / +z). The weights all go to
  `weapon_offset`.
- `build.bat` is the full rebuild. The paths in it need editing for this PC.

## Files that only existed in the cloud session (gone)

- `d4c_fit.blend` (D4C on Doorman's skeleton): replaced by `props/d4c_posed.glb`, already posed
  with `doorman_generic_cast_channeling_loop` at 0.5, centred, feet at 0, facing +X.
  - A different pose needs the fit again:
    `fv_build.py --pick Armature.001 --exclude icosphere --keep-mats none --save-blend ...` into a
    scratch hero folder.
  - Then `d4c_prop.py --fitted ... --anim <decompiled doorman_v2 anim .dmx> --save-posed ...`.
  - The animation `.dmx` files come from decompiling `doorman.vmdl_c` (Source 2 Viewer).
- The Gappy mod: re-download from GameBanana if you need to compare.

## Working with this user

- They want it done *for* them: minimal manual steps, and exact click-by-click instructions when
  a step is unavoidable. Screenshots are their main feedback channel.
- Commit with clear messages and push to the branch above. They share builds with friends
  through the release.
