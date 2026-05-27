// js/lib/colors.js
// Génère une couleur HSL déterministe à partir d'un string (username) pour
// avoir des avatars cohérents même si `avatar_color` en DB venait à manquer.

export function colorFromString(s) {
    let hash = 0;
    for (let i = 0; i < s.length; i++) {
        hash = s.charCodeAt(i) + ((hash << 5) - hash);
    }
    return `hsl(${Math.abs(hash) % 360}, 65%, 55%)`;
}

export function avatarHtml(profile, size = 32) {
    const color = profile?.avatar_color || colorFromString(profile?.username || '?');
    const initial = (profile?.username || '?')[0].toUpperCase();
    return `<span class="avatar" style="background:${color};width:${size}px;height:${size}px;line-height:${size}px;font-size:${size * 0.45}px">${initial}</span>`;
}
