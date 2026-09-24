# Funny Valentine (JJBA Part 7) → Doorman

The 23rd President of the United States replaces Doorman. He keeps Doorman's key-gun,
doors and every animation, so he plays exactly like Doorman does. It fits: D4C hops
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

## Steps

1. **Get the model.** Download
   [FUNNY VALENTINE & D4C || SBR by shamus](https://sketchfab.com/3d-models/funny-valentine-d4c-sbr-2a19d4e917184ba3addc8f0b2f7c14ee)
   from Sketchfab. It's free and rigged, but you need a free Sketchfab account.
   Pick **glTF**, then unzip it into `funny_valentine/source/` so that
   `source/scene.gltf` exists. That folder is git-ignored.

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

## Options worth knowing

| flag | what it does |
|---|---|
| `--with-stand` | Brings D4C along, floating over his shoulder. It's rigid and stuck in whatever pose the file has, which is funnier than it should be. |
| `--scale 1.05` | Makes him bigger or smaller than Doorman. |
| `--pick valentine` | Picks which armature is FV if the script grabs D4C instead. |
| `--exclude d4c,outline,hat` | Drops FV-side meshes whose object or material name contains any of these. |
| `--bone-map map.json` | Tells it which bone is which if auto-matching fails (see `bone_map.example.json`). |
| `--weights hero` | Copies Doorman's skin weights by proximity instead of using FV's own. Try it if his clothes deform badly. |
| `--save-blend x.blend` | Saves the fitted scene so you can fix weights by hand. Re-export with BST as DMX binary 9, model 22. |

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

- Model: "FUNNY VALENTINE & D4C || SBR" by **shamus (@consistent_models)** on
  Sketchfab, licensed **CC BY 4.0**. Keep this credit if you upload the mod anywhere.
- Funny Valentine / JoJo's Bizarre Adventure © Hirohiko Araki. This is a non-commercial fan mod.
