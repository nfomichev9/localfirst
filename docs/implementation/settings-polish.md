# Settings polish

November 20, 2026. Rework the existing Settings frontend into a restrained desktop
dialog with side navigation and compact, divided rows. Keep two useful sections:
Chat (existing four routing modes/provider readiness) and Spending (existing daily
limit, used/reserved usage, link to analytics). Keep backend/preferences unchanged.

Use native select/number/checkbox controls, scoped CSS, real keyboard-accessible tabs,
Escape/close back to chat, responsive mobile layout, loading/error/retry states,
dirty-state save/reset, and existing explicit consent for automatic/cloud-only modes.
Cloud configuration is read-only; no fake connect/account/theme/notification controls.
Show unavailable usage honestly. Preserve configured modes when provider setup is
missing; allow switching back to local. Do not save on navigation or load.

Verify real local preference persistence, validation/consent, tab keyboard behavior,
provider-unavailable states, save/load failures and recovery, mobile layout and actual
desktop/mobile renders. No inference or paid requests are needed for this change.
