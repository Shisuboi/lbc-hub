// js/lib/transactions.js
// Couche d'accès aux transactions financières de l'utilisateur courant.
// RLS garantit côté serveur qu'un user ne touche que ses propres lignes ;
// on passe quand même user_id à l'insert (la policy with-check l'exige).
import { supa } from '../supabase-client.js';

/** Récupère toutes les transactions du user courant, triées par date décroissante. */
export async function listTransactions() {
    const { data, error } = await supa
        .from('transactions')
        .select('id, type, label, amount, date, search_id, url, created_at')
        .order('date', { ascending: false })
        .order('created_at', { ascending: false });
    if (error) throw new Error('Chargement des transactions impossible : ' + error.message);
    return data || [];
}

/** Crée une transaction. Renvoie la ligne insérée. */
export async function createTransaction(input) {
    const { data: { session } } = await supa.auth.getSession();
    const user = session?.user;
    if (!user) throw new Error('Non authentifié. Reconnecte-toi.');

    const row = {
        user_id: user.id,
        type: input.type,
        label: String(input.label || '').trim().slice(0, 200),
        amount: Number(input.amount),
        date: input.date,
        search_id: input.search_id || null,
        url: input.url?.trim() || null,
    };

    const { data, error } = await supa
        .from('transactions')
        .insert(row)
        .select()
        .single();
    if (error) throw new Error('Création impossible : ' + error.message);
    return data;
}

/** Met à jour une transaction existante (champs éditables uniquement). */
export async function updateTransaction(id, input) {
    const patch = {
        type: input.type,
        label: String(input.label || '').trim().slice(0, 200),
        amount: Number(input.amount),
        date: input.date,
        search_id: input.search_id || null,
        url: input.url?.trim() || null,
    };
    const { data, error } = await supa
        .from('transactions')
        .update(patch)
        .eq('id', id)
        .select()
        .single();
    if (error) throw new Error('Mise à jour impossible : ' + error.message);
    return data;
}

/** Supprime une transaction. */
export async function deleteTransaction(id) {
    const { error } = await supa.from('transactions').delete().eq('id', id);
    if (error) throw new Error('Suppression impossible : ' + error.message);
}

/**
 * Agrège une liste de transactions en KPIs financiers.
 * @returns {{ invested:number, earned:number, profit:number, roi:number|null,
 *             buyCount:number, sellCount:number }}
 */
export function computeKpis(transactions) {
    let invested = 0, earned = 0, buyCount = 0, sellCount = 0;
    for (const t of transactions) {
        const amount = Number(t.amount) || 0;
        if (t.type === 'achat') { invested += amount; buyCount += 1; }
        else if (t.type === 'vente') { earned += amount; sellCount += 1; }
    }
    const profit = earned - invested;
    // ROI = profit / investi. Indéfini si rien n'a été investi.
    const roi = invested > 0 ? (profit / invested) * 100 : null;
    return { invested, earned, profit, roi, buyCount, sellCount };
}

/**
 * Construit les séries mensuelles pour les graphiques.
 * Renvoie les mois (YYYY-MM) triés croissants avec, pour chacun :
 *  - achats / ventes du mois, et le cumul d'achats / ventes jusqu'au mois inclus.
 * @returns {{ labels:string[], buysCumul:number[], sellsCumul:number[], profitMonthly:number[] }}
 */
export function buildMonthlySeries(transactions) {
    const byMonth = new Map(); // 'YYYY-MM' -> { buy, sell }
    for (const t of transactions) {
        if (!t.date) continue;
        const month = String(t.date).slice(0, 7); // YYYY-MM
        if (!byMonth.has(month)) byMonth.set(month, { buy: 0, sell: 0 });
        const bucket = byMonth.get(month);
        const amount = Number(t.amount) || 0;
        if (t.type === 'achat') bucket.buy += amount;
        else if (t.type === 'vente') bucket.sell += amount;
    }

    const labels = [...byMonth.keys()].sort();
    const buysCumul = [];
    const sellsCumul = [];
    const profitMonthly = [];
    let cumulBuy = 0, cumulSell = 0;
    for (const month of labels) {
        const { buy, sell } = byMonth.get(month);
        cumulBuy += buy;
        cumulSell += sell;
        buysCumul.push(cumulBuy);
        sellsCumul.push(cumulSell);
        profitMonthly.push(sell - buy);
    }
    return { labels, buysCumul, sellsCumul, profitMonthly };
}

/** Formate un mois 'YYYY-MM' en libellé court FR (ex: 'juin 2026'). */
export function formatMonthLabel(ym) {
    const [y, m] = ym.split('-').map(Number);
    const d = new Date(y, (m || 1) - 1, 1);
    return d.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' });
}
