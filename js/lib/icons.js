// js/lib/icons.js
// Jeu de pictogrammes SVG (style Lucide/Feather, trait régulier) — AUCUN emoji.
// icon(name, { size, cls }) → chaîne HTML <svg>. stroke = currentColor.

const PATHS = {
  home:    '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
  heart:   '<path d="M20.8 5.1a5 5 0 0 0-7.1 0L12 6.8l-1.7-1.7a5 5 0 1 0-7.1 7.1L12 21l8.8-8.8a5 5 0 0 0 0-7.1z"/>',
  radar:   '<path d="M22 12h-4l-3 8L9 4l-3 8H2"/>',
  chart:   '<path d="M3 20h18"/><path d="M6 20v-5"/><path d="M12 20V8"/><path d="M18 20v-9"/>',
  sliders: '<path d="M4 21v-6"/><path d="M4 11V3"/><path d="M12 21v-9"/><path d="M12 7V3"/><path d="M20 21v-4"/><path d="M20 13V3"/><path d="M2 13h4"/><path d="M10 7h4"/><path d="M18 17h4"/>',
  user:    '<circle cx="12" cy="8" r="4"/><path d="M5.5 21a7 7 0 0 1 13 0"/>',
  search:  '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-3.6-3.6"/>',
  image:   '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.8"/><path d="m21 15-4.5-4.5L5 21"/>',
  pin:     '<path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/>',
  clock:   '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  logout:  '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  bolt:    '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
};

export function icon(name, { size = 24, cls = '' } = {}) {
  const d = PATHS[name] || '';
  return `<svg class="ico${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" width="${size}" height="${size}"`
    + ` fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
}
