# Brander assets

Wallpaper backgrounds for the **Brander (Tap Action)** template.

- `lockscreen-template.png` — default background when no role matches.
- `null.png` — background when the device has no role set.
- `brandlogo.png` — reserved for a logo overlay (not composited by default).
- `jawa-logo.png` — the JAWA logo (1024 px), used by the example templates as the `jawa-logo` asset.
- `<role>.png` — one background per role, matched case-insensitively against
  the Jamf Setup extension attribute value with spaces removed
  (`Video Conferencing` → `videoconferencing.png`). The six shipped role images
  are examples; replace them with your own at the same size.

Text is rendered with Pillow's built-in font unless the template's
"Font file path" setting points at a `.ttf`/`.otf` you supply. No font ships
here.

## Templates (optional)

Instead of the layout above, Brander can render a **wallpaper template**: a
JSON file designed in EWOK and rendered by the same code (`wallrender`,
vendored and hash-pinned in `data/workflows/lib`), so the preview is what the
device receives.

- Set the template's "Wallpaper template" setting to a JSON path, absolute or
  relative to this directory. `legacy` (the default) keeps the original
  layout. Two starting points ship here:
  - `example-template.json`: iPhone, portrait (1290x2796).
  - `example-ipad-template.json`: iPad, square 2732x2732 with everything in
    the centre 75%, which stays visible in both portrait and landscape.
    iOS scales a wallpaper to fill the screen and crops the rest, so a
    portrait iPhone template loses its top and bottom on an iPad.
- Templates uploaded to JAWA's **template store** (a `.brander.json` package
  exported from EWOK) are used by setting "Wallpaper template" to
  `store:<name>`. Brander renders that template's **active** version with its
  own assets, so activating a new version takes effect on the next tap.
- A **store set** sends each kind of device its own stored template:
  `store:iphone=front-desk ipad=ward-ipads`. Pairs are separated by spaces;
  keys are an exact model identifier (`iPad8,5`), a family (`iphone`,
  `ipad`) or `default`, tried in that order, the same as a template set
  file. The store page shows which layers each family's screens cut off or
  cover, for the active version and for each upload.
- A template may say which screen it is for (`"screen": "lock"`, `"home"` or
  `"both"`). That choice wins over the Brander's "wallpaper target" setting.
- Image layers name an asset id; Brander loads `<id>.png`, `.jpg` or `.jpeg`
  from this directory and nowhere else.
- A template can print only these fields of the UDID-verified Jamf record:
  `{{device_name}}`, `{{serial_number}}`, `{{asset_tag}}`, `{{jss_id}}` and
  `{{location.building}}`. Anything else renders empty. Nothing from the
  request that triggered Brander is ever printed.
- A template with **role variants** (designed in EWOK) names an extension
  attribute, such as "Jamf Setup Role". Brander reads that one attribute from
  the verified record and passes it as the role, so each role can have its own
  background and wording. No other extension attribute is read.
- **Personal fields** (`{{user.real_name}}`, `{{user.username}}`,
  `{{user.email}}`) print only when the template sets `person_fields: true`
  *and* this Brander's "Allow personal fields" setting is `yes` (default `no`).
  Otherwise they render empty. They are never allowed in QR codes.
- Rendering stops after 20 seconds (exit 33). The image is sent as PNG, or as
  JPEG when the PNG is over the "Largest wallpaper" setting (default 1500 KB);
  exit 34 if even JPEG is too large.

To update the renderer, run `bin/vendor_wallrender.py` against an EWOK
checkout. Never edit `data/workflows/lib/wallrender` by hand: Brander refuses
to run an edited copy (exit 31).

## Asset Tag Watch

Templates print `{{asset_tag}}`, so a device that is re-tagged keeps showing
its old tag until it is branded again. The **Brander (Asset Tag Watch)**
template does that for you. It is a timed automation (every 15 minutes by
default; change the schedule on its edit page) that reads every mobile device
from Jamf Pro and runs your installed **Brander (Tap Action)** script for each
device whose asset tag or "Brander" extension attribute changed.

- Enable Brander (Tap Action) first. Asset Tag Watch runs that script, so the
  wallpaper settings, templates and checks are the ones it already has. Its
  "Brander script path" setting defaults to
  `/usr/local/jawa/scripts/brand-device.py`, where enabling Brander
  (Tap Action) under its default name puts the script. If you named it
  something else, the path is on that automation's detail page.
- The asset tag is the first non-empty of asset tag, barcode 1 and barcode 2.
  `null`, `none`, `n/a` and blank all count as empty.
- The first run only records what it sees. Nothing is branded until a device
  changes after that.
- A change is stored once Brander has dealt with it: it set the wallpaper, or
  the device cannot take one (Brander EA Off, not supervised, not iOS or
  iPadOS). Any other failure is retried on the next run, and the run exits 2,
  which the JAWA log records as a failed run and which sends the chat failure
  alert set on Setup. Exit 1 means the device list could not be read;
  nothing is stored.
- "Dry run" set to `yes` prints which devices would be branded and why, and
  stores nothing for them.
- State is a SQLite file (default `/usr/local/jawa/data/asset_tag_watch.sqlite`).
  Delete it to start over; the next run seeds again.
- Its API client needs only **Read Mobile Devices**. The Brander's own client
  sends the wallpaper.
- Each run reads every device record, one API call per device. On a large
  fleet, choose a schedule that leaves the run time to finish. A run that starts
  while the previous one is still going skips itself, so no device is branded
  twice.
