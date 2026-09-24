# Funny Valentine (JJBA Part 7) → Doorman

The 23rd President of the United States replaces Doorman. He carries his own revolver
instead of the key-gun and keeps Doorman's doors and every animation, so he plays exactly
like Doorman does. It fits: D4C hops
between worlds by getting sandwiched between things, and Doorman's whole kit is doors.

The lazy part is `fv_build.py`. It's a Blender script that does the whole "pain and
suffering" step (posing the new model to match, deleting its armature, transferring
weights, fixing names, exporting the DMX) automatically:

- matches FV's bones to Doorman's by name (Mixamo, Rigify, MMD/Japanese, VRM and
  Sketchfab's `_NN` suffixes all work)
- turns him to face +X and scales him to Doorman's height
- warps the mesh so his shoulders, elbows, wrists, hips, knees and ankles sit exactly
  on Doorman's joints, in Doorman's A-pose. The gun ends up in his hands.
- renames his own skin weights onto Doorman's bones. The skeleton itself is left
  alone, so the stock animgraph works as-is.
- cuts Doorman's gun and door props out of his body mesh and puts them on FV
- writes `funny_valentine.dmx`, the `.vmat` and `.png` material files, and patches
  `doorman.vmdl`: body swapped for FV and the head mesh removed. Everything else
  stays: hitboxes, attachments, physics, AG2 nodes.

## You need

The same tools you used for the Billy mod:

- **Blender 4.1+** with **[Blender Source Tools](https://github.com/Artfunkel/BlenderSourceTools/releases)** enabled
- **Source 2 Viewer**, **CSDK12**, **CSWin64** (CS2 workshop tools)
- **[Deadlock VMDL Compiler](https://github.com/kwlnd/deadlock-vmdl-compiler/releases)**
  (it injects the AG2 skeleton/animgraph and compiles in CSWin64)

## Quick route (prebuilt)

If you have `funny_valentine_addon.zip` (the ready-made addon folder with the FV
model, materials and patched `doorman.vmdl`), skip straight to steps 4–5: unzip it
into `CSDK12/content/citadel_addons/`, so you get
`citadel_addons/funny_valentine/models/...`, then compile and pack.

## Steps (building it yourself)

1. **Get the model.** Download
   [FUNNY VALENTINE & D4C || SBR by shamus](https://sketchfab.com/3d-models/funny-valentine-d4c-sbr-2a19d4e917184ba3addc8f0b2f7c14ee)
   from Sketchfab. It's free and rigged, but you need a free Sketchfab account.
   glTF or the original `.blend` both work. If the `.blend` can't find its
   textures, the script finds same-named files in a nearby `textures/` folder
   (or pass `--textures`).

2. **Decompile Doorman.** In CSDK12, make a new addon called `funny_valentine`. In
   Source 2 Viewer, open `Deadlock/game/citadel/pak01_dir.vpk`, go to
   `models/heroes_wip/doorman_v2/`, and decompile `doorman.vmdl_c` into
   `CSDK12/content/citadel_addons/funny_valentine/models/heroes_wip/doorman_v2/`.
   You should end up with `doorman.vmdl` and `doorman_doorman.dmx` in that folder.

3. **Run the script.** Edit the three paths at the top of `build.bat` and
   double-click it. Or run it directly:

   ```
   blender -b -P fv_build.py -- --model source/scene.gltf --hero-dir "C:/CSDK12/content/citadel_addons/funny_valentine/models/heroes_wip/doorman_v2" --preview fv_preview --save-blend fv_fitted.blend
   ```

   Open `fv_preview_front.png` / `fv_preview_side.png` and check he's standing
   in Doorman's A-pose at the right size. `fv_fitted.blend` has him on the
   skeleton if you want to poke at anything.

4. **Compile the materials.** In CSDK12, right-click the addon and choose
   **Compile All Assets**. This builds `materials/funny_valentine/*.vmat`.

5. **Compile the model and pack.** Open Deadlock VMDL Compiler and pick addon
   `funny_valentine`, model `doorman.vmdl`, preset **doorman**. Click **compile**,
   then **make vpk...**. Drop the `pakXX_dir.vpk` into `Deadlock/game/citadel/addons/`
   like any other mod.

## D4C in the Hotel

While someone is checked into the Hotel (Doorman's ult), D4C floats beside you, just behind your
left shoulder, facing where you aim. He appears the moment they're checked in and vanishes the
moment they come out, whether that's the full stay, a shorter or longer one from items, or an
early checkout. He sits on the left because the camera looks over your right shoulder; anywhere
behind or to the right puts him in front of the crosshair.

How: the game puts `particles/abilities/doorman/doorman_hotel_debuff.vpcf` on the victim's
stand-in for exactly as long as they're in the Hotel. `addon_files/` overrides it with Valve's
same effect plus one extra child, `particles/funny_valentine/d4c_hotel.vpcf`. That child copies
the lifecycle of Valve's own floating key: one particle whose lifetime only runs out when the game
ends the effect, so it has no timings of its own. D4C himself is a static prop
(`models/heroes_wip/doorman_v2/fv_d4c_hotel.vmdl`), posed by `d4c_prop.py`, with the "beside the
left shoulder" offset built into the mesh.

An effect can't tell which player is Doorman: all it knows is the victim and the local player
(whoever's screen it is). So D4C follows the local player. When you're Doorman that's you. A friend
who also has the mod but is playing someone else would see D4C next to *their* hero while the
victim's stand-in is nearby.

To add it, copy `addon_files/` into the addon (`tools/Install FV update.bat` does that and stamps the
files so the compilers pick them up). Then:

1. CSDK12: **Compile All Assets** (materials and the two effects).
2. VMDL Compiler: `doorman.vmdl` with preset **doorman** → **compile**.
3. VMDL Compiler: `fv_d4c_hotel.vmdl` → **compile**. It's a plain prop and has no skeleton, so
   nothing gets injected.
4. `tools/Check FV update.bat` lists anything that still isn't built. Then **make vpk...**.

If Valve changes the Hotel effect, re-extract it with `tools/Extract Doorman door.bat` and add the
D4C child to the new copy.

## Sharing it with friends

Once you have the compiled `.vpk` from step 5:

1. Upload it at
   **https://github.com/idkbro757/deadlock-mods/upload/claude/brave-pasteur-17l5q5/funny_valentine/release**
   (drag it in, then click **Commit changes**).
2. About a minute later, a GitHub Action publishes it as a download at
   **https://github.com/idkbro757/deadlock-mods/releases/tag/funny-valentine**. Send your friends that link.

Friends download `FunnyValentine-Deadlock.zip`, unzip it, and double-click
**Install Funny Valentine.bat**. The installer finds Deadlock through Steam, turns on
mod loading in `gameinfo.gi` (keeping a `.bak`), and copies the mod into a free
`citadel/addons/pakNN_dir.vpk` slot without touching their other mods. Deadlock
updates reset `gameinfo.gi`, so they just run it again afterwards. There's an
uninstaller next to it too. Upload a newer vpk and the release updates itself.

Mods are visual only: each friend sees FV only if they installed it themselves.

## Options worth knowing

| flag | what it does |
|---|---|
| `--gun props/fv_revolver.glb` | Swaps Doorman's key-gun for another gun model (`build.bat` uses FV's own revolver). The grip goes in his palm and the barrel lies along Doorman's barrel. |
| `--gun-forward -y --gun-up +z` | Tells it which way the `--gun` model's barrel and top face if it guesses wrong. |
| `--gun-scale 1.1` | Makes the `--gun` bigger or smaller. |
| `--with-stand` | Brings D4C along, floating over his shoulder. It's rigid and stuck in whatever pose the file has, which is funnier than it should be. |
| `--scale 1.05` | Makes him bigger or smaller than Doorman. |
| `--pick valentine` | Picks which armature is FV if the script grabs D4C instead. |
| `--exclude d4c,outline,hat` | Drops FV-side meshes whose object or material name contains any of these. |
| `--bone-map map.json` | Tells it which bone is which if auto-matching fails (see `bone_map.example.json`). |
| `--weights hero` | Copies Doorman's skin weights by proximity instead of using FV's own. Try it if his clothes deform badly. |
| `--save-blend x.blend` | Saves the fitted scene so you can fix weights by hand. Re-export with BST as DMX binary 9, model 22. |

**Compiler fails with `content_consider_missing_materials_fatal` (9 errors)?** Recent
CS2 builds treat any missing material as fatal when compiling a `.vmdl`, and CS2 doesn't
have Deadlock's materials. Open
`...\Counter-Strike Global Offensive\game\csgo_core\gameinfo.gi` in Notepad, search for
`content_consider_missing_materials_fatal`, change the `"substr" ".vmdl"` line under it
to `"substr" ".nomatch"`, save, and compile again. A CS2 update may undo it, so redo the
edit if the error comes back.

The script prints the bone match it found. If it says
`couldn't find arms/legs/head/hips`, it falls back to scaling him to fit and
copying Doorman's weights. That works, but a T-posed model will look rough.
Write a `--bone-map` for the main bones to fix it.

## Other heroes

Nothing here is Doorman-specific. Point `--hero-dir` at any hero's decompile and
use that hero's preset in the compiler. For example, Billy is
`models/heroes_wip/punkgoat/` and Haze is `models/heroes_staging/haze/`. If the
hero's weapon isn't a separate material on the body, pass `--keep-mats` with its
material name. If the hero has extra render meshes to hide, pass them to `--drop`.

## Credits

- Model: "FUNNY VALENTINE & D4C || SBR", uploaded to Sketchfab by **shamus (@consistent_models)**.
- Revolver (`props/fv_revolver.glb`): from the SFM "Funny Valentine & D4C" pack
  ([Steam Workshop 1655983213](https://steamcommunity.com/sharedfiles/filedetails/?id=1655983213)),
  which ports the same game models.
  It's killermemerino's XNALara port of the model from *JoJo's Bizarre Adventure: All-Star
  Battle / Eyes of Heaven* (Bandai Namco / CyberConnect2), so credit them too if you share it.
- Funny Valentine / JoJo's Bizarre Adventure © Hirohiko Araki. This is a non-commercial fan mod.
