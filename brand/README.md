# Donkey Development Kit — brand assets

The official logo set for **Donkey Development Kit (DDK)**.

> *Takes the donkey work out of AI development.*

The mark is a donkey/bunny-eared head paired with the **DDK** wordmark.

## Files

| File | Wordmark | Layout | Theme | Suggested use |
| --- | --- | --- | --- | --- |
| [`ddk-logo-horizontal-duo.png`](ddk-logo-horizontal-duo.png) | DDK | Horizontal lockup (mark + wordmark) | Dark + light pair | **Primary logo.** Headers, README, nav bars. Crop the half that fits your background. |
| [`ddk-logo-stacked-duo.png`](ddk-logo-stacked-duo.png) | DDK | Square / stacked (mark over wordmark) | Dark + light pair | Square spaces — avatars, app icons, social cards. |
| [`ddk-logo-chalkboard.png`](ddk-logo-chalkboard.png) | DDK | Horizontal, chalk texture | White chalk on black | Hero banners, decorative headers, slides. |

The `-duo` files contain **both** a dark-background and a light-background
treatment in one image; crop to the variant that suits your surface.

## Usage notes

- Prefer the **horizontal DDK lockup** as the default logo everywhere the
  brand appears.
- Keep clear space around the mark equal to the height of the wordmark's
  cap-height; don't crowd it with other elements.
- Don't recolor, stretch, rotate, or add effects to the mark — pick the
  dark or light treatment that already matches your background.
- These are raster (PNG) source art. A vector (SVG) master is not yet
  part of this set; regenerate one before print or large-format use.

## Not yet wired in

These assets are added to the repo but are **not** yet referenced by the
docs site (`website/theme.config.tsx` logo/favicon) or the top-level
`README.md`. Wiring them into those surfaces is intentionally a separate
change.
