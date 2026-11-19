# Brander guide

Brander puts a branded wallpaper on a supervised iPad or iPhone. The wallpaper shows the device's
name, serial number, asset tag and building, and a QR code of its Jamf Pro id. The person holding
the device starts it by tapping a web clip, so IT does not have to touch the device.

Brander ships as two templates:

- **Brander (Tap Action)** sets the wallpaper when someone taps the web clip.
- **Brander (Asset Tag Watch)** runs on a schedule and re-brands any device whose asset tag
  changed. It is optional, and it uses the Tap Action's script.

This guide covers the setup, a first test, and changes to the design. For every setting and
exit code, see `data/workflows/assets/brander/README.md`.

## Before you start

- **Devices:** iOS or iPadOS, supervised, and enrolled in Jamf Pro. Wallpapers need
  supervision, so Brander refuses other devices (exit 25 or 26).
- **An API client in Jamf Pro** with a role that has these two privileges:
  - Read Mobile Devices
  - Send Mobile Device Set Wallpaper Command

  Keep its client ID and secret ready.
- **Optional extension attributes on mobile devices:**
  - **Brander**. A device with this attribute set to `Off`, or left empty, is never branded
    (exit 42). Use it to opt devices out.
  - **A role attribute**, for example "Jamf Setup Role". Brander picks a background image for each
    role. You enter this attribute's Jamf Pro id when you enable the template. Leave it at `0` to
    give every device the same wallpaper.

## 1. Enable Brander (Tap Action)

1. In JAWA, open **Templates** and choose **Brander (Tap Action)**, then **Enable Template**.
2. Fill in the settings:

   | Setting | What to enter |
   |---|---|
   | Jamf Pro URL, OAuth Client ID, OAuth Client Secret | The API client from "Before you start". |
   | Jamf Setup role extension attribute ID | The role attribute's id, or `0`. |
   | Wallpaper target | `1` lock screen, `2` home screen, `3` both. |
   | Assets directory | Leave the default to start. See "Use your own images" below. |
   | Font file path | `none`. |
   | Wallpaper template | Leave `legacy` to start. See "Change the design" below. |
   | Allow personal fields | `no`, unless a template must print the user's name or email. |
   | Largest wallpaper to send, in KB | Leave `1500`. |

3. Save. JAWA tries to create the web clip configuration profile in Jamf Pro for you. The profile
   is not scoped yet. If Jamf Pro refuses to create it, the automation's detail page shows the web
   clip URL, so you can build the profile by hand.

## 2. Scope the web clip

In Jamf Pro, scope the new web clip profile to a test device first. When the profile arrives, the
web clip appears on the home screen with its own label and icon.

## 3. Check the wallpaper before you tap

Open **Extras → Brander preview**. Choose a template and enter the Jamf Pro id of a test device.
JAWA reads that device's real record and shows the wallpaper it would send. Nothing is sent to the
device.

## 4. Tap it

On the test device, tap the web clip, check the confirmation page, and confirm. The wallpaper can
take a minute to appear.

- A device can be branded only once every 5 minutes. **Reset cooldowns** on the automation's page
  in JAWA clears this.
- If it fails, the person sees "The wallpaper could not be applied. Please tell IT." Open the
  **Log** in JAWA. The exit code tells you why. Common ones: 20, the device did not match its own
  record; 24, Jamf Pro refused the wallpaper command (check the API role); 25, the device is not
  supervised.

When the test device looks right, scope the profile to the rest of the devices.

## Use your own images

The shipped backgrounds are examples. Keep your own images in a folder of your own, not in the
shipped folder, so a JAWA update and your changes never touch the same files:

```sh
sudo cp -R /usr/local/jawa/data/workflows/assets/brander \
  /usr/local/jawa/data/brander-assets
sudo chown -R jawa /usr/local/jawa/data/brander-assets
```

Then set **Assets directory** to `/usr/local/jawa/data/brander-assets` on the automation's edit
page.

With the `legacy` layout, the background comes from the device's role:

- `<role>.png` for a device with a role. The role value is matched in lower case with spaces
  removed, so `Video Conferencing` uses `videoconferencing.png`.
- `null.png` for a device with no role.
- `lockscreen-template.png` for a role that has no image.

Keep each image the same size as the example you replace.

## Change the design

A **wallpaper template** is a JSON file that controls the layout: background, text, images and the
QR code. Two ship in the assets folder:

- `example-template.json`: iPhone, portrait, 1290 × 2796.
- `example-ipad-template.json`: iPad, 2732 × 2732. Everything sits in the centre, so it stays
  visible in portrait and in landscape.

To use one, set **Wallpaper template** to its file name, for example `example-ipad-template.json`.
To give each kind of device its own template, use a set file such as `example-set.json`, which
names a template for `iphone`, `ipad` and `default`.

### Edit a template

Copy the example into your own assets folder and edit the copy. Each layer has a `type` (`text`,
`image`, `qr` or `panel`) and a `box`. Positions and sizes are fractions of the canvas: `x` and
`y` place the top-left corner, and `w` and `h` set the size. A text layer's `size` is a fraction of
the canvas height.

```json
{"type": "text", "text": "Asset {{asset_tag}}",
 "box": {"x": 0.14, "y": 0.575, "w": 0.72, "h": 0.04},
 "size": 0.025, "color": "#D6E2F0", "align": "center",
 "overflow": "ellipsis", "hide_if_empty": true}
```

- `align`: `left`, `center` or `right`.
- `overflow`: `shrink` or `ellipsis`, for text that is too long for its box. With `shrink`,
  `min_size` sets the smallest size.
- `hide_if_empty`: leaves out a layer whose value is empty.
- Colours are `#RRGGBB` or `#RRGGBBAA`.
- An `image` layer's `asset` is a file name without its extension (`jawa-logo` loads
  `jawa-logo.png`). Brander loads images only from the assets directory.

A template can print only these fields from the device's Jamf Pro record: `{{device_name}}`,
`{{serial_number}}`, `{{asset_tag}}`, `{{jss_id}}` and `{{location.building}}`. Any other field
prints empty.

### Check a template on the server

Before you point Brander at a changed template, render it with sample values:

```sh
cd /usr/local/jawa/data/brander-assets
echo '{"device_name": "iPad-0142", "serial_number": "F9FXK2ABCD"}' \
  > /tmp/values.json
PYTHONPATH=/usr/local/jawa/data/workflows/lib \
  /usr/local/jawa/venv/bin/python -m wallrender preview \
  my-template.json /tmp/values.json -o /tmp/preview.png --stress
```

The command prints what to fix. `--stress` also renders a copy with every value long and a copy
with every value empty, so you can check text that does not fit. `PYTHONPATH` points Python at
the copy of `wallrender` that Brander itself uses. Then check the result with a real device in **Extras → Brander preview**.

### The template store

**Extras → Brander templates** keeps uploaded templates (`.brander.json` packages, which bundle a
template with its images) as cards with a preview, and keeps their earlier versions. To use a
stored template, set **Wallpaper template** to `store:<name>`. Brander always uses the active
version, so a newly activated version applies from the next tap.

## Keep asset tags current (optional)

A wallpaper shows the asset tag from when the device was branded. To re-brand devices when their
tag changes, enable **Brander (Asset Tag Watch)** after the Tap Action. Its API client needs only
Read Mobile Devices. It reads every device on each run, so on a large fleet choose a schedule that
gives a run time to finish. Its first run only records the current tags; it brands nothing until a
tag changes.
