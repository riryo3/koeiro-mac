# Koeiro PV (Remotion)

The source of the promo video: the composition, the camera that aims at the app's own
click targets, and the scripts that generate its sound.

Two compositions are registered: `KoeiroPV` (the video) and `HotspotCheck` (the click
boxes drawn over a captured screen, used to check that the camera aims at the right
widget before a render).

## Commands

```console
npm i --loglevel=error
npm run dev                                        # Remotion Studio
npx remotion render KoeiroPV out/koeiro-pv.mp4
npm run lint
```

## Assets

`public/` is not in git. Everything in it is generated, except the owner's own
recording, which is never published.

| Path | Made by |
| --- | --- |
| `public/audio/` SFX | `npm run sfx` |
| `public/audio/voice_demo_*.wav` | `npm run voice`, from `public/raw/voice_source.mp3` (the owner's voice, kept private) |
| `public/brand/icon.png`, `logo.png` | copied from `../assets/` |
| `public/brand/logo_trimmed.png` | `npm run brand` (ffmpeg crop of `assets/logo.png`) |
| `public/brand/splash.mp4` | `.venv/Scripts/python.exe tools/render_splash.py` |
| `public/raw/*.mp4` | `tools/pv_take.py` — OBS window capture, see [notes/promo_take_obs.md](../notes/promo_take_obs.md) |
| `public/meta/*.json` | written alongside the take: cue offset, marks, hotspot boxes |

The cut is built from a real take rather than a mock-up: `tools/promo_run.py` drives the
shipped window through its recorded steps and `tools/obs_record.py` records it, so the
frames the edit moves over are frames the app produced.

## License

Remotion requires a company licence for some entities. [Read the terms](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)
before distributing a render made here.
