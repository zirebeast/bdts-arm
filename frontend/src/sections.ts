// Оценка допуска и статус раздела результата ДО. Логика совпадает с backend app/services/sections.py
export type Tol = 'ok' | 'borderline' | 'exceeded' | 'empty';
const RANK: Record<Tol, number> = { empty: 0, ok: 1, borderline: 2, exceeded: 3 };

const s = (v: any) => (v === null || v === undefined ? '' : String(v).trim());
const num = (v: any): number | null => {
  const x = parseFloat(s(v).replace(',', '.'));
  return Number.isFinite(x) ? x : null;
};

export function tolField(spec: any, v: any): Tol | null {
  if (!spec) return null;
  if (spec.t === 'map') return (spec.m[s(v)] as Tol) || 'empty';
  const x = num(v);
  if (s(v) === '' || x === null) return 'empty';
  if (spec.t === 'gt') return x > spec.v ? 'exceeded' : 'ok';
  if (spec.t === 'ge_ok') return x >= spec.v ? 'ok' : 'borderline';
  return null;
}

export function tolRow(spec: any, r: any): Tol {
  switch (spec.t) {
    case 'doc': { const st = s(r.st); return !st ? 'empty' : st === 'Не предоставлен' ? 'borderline' : 'ok'; }
    case 'col': return (spec.m[s(r[spec.c])] as Tol) || 'empty';
    case 'cols': {
      const vals: Tol[] = spec.cs.map(([c, m]: [string, any]) => (m[s(r[c])] as Tol) || 'empty');
      return vals.includes('empty') ? 'empty' : vals.reduce((a, b) => (RANK[b] > RANK[a] ? b : a));
    }
    case 'vol_col': { const vol = num(r[spec.vol]); if (s(r[spec.vol]) && vol !== null && vol < spec.min) return 'borderline'; return (spec.m[s(r[spec.c])] as Tol) || 'empty'; }
    case 'bands': case 'abs_bands': {
      let x = num(r[spec.c]);
      if (x === null) return 'empty';
      if (spec.t === 'abs_bands') x = Math.abs(x); else if (x < 0) return 'empty';
      return x > spec.bad ? 'exceeded' : x > spec.warn ? 'borderline' : 'ok';
    }
    case 'range': { const x = num(r[spec.c]); if (x === null) return 'empty'; return x >= spec.lo && x <= spec.hi ? 'ok' : 'exceeded'; }
    case 'plan_fact': { const p = num(r.plan); const f = num(r.fact); if (s(r.fact) === '') return 'empty'; return p !== null && f !== null && f < p ? 'borderline' : 'ok'; }
    case 'nonempty': return s(r[spec.c]) ? 'ok' : 'empty';
    default: return 'empty';
  }
}

export function tolThk(v: any, sCalc: number): Tol {
  const x = num(v);
  if (x === null || x <= 0) return 'empty';
  if (x < sCalc) return 'exceeded';
  return x <= 1.08 * sCalc ? 'borderline' : 'ok';
}

export function tolHb(v: any, lo: number, hi: number): Tol {
  const x = num(v);
  if (x === null || x <= 0) return 'empty';
  if (x < lo || x > hi) return 'exceeded';
  return x <= lo + 8 || x >= hi - 8 ? 'borderline' : 'ok';
}

export function pointTol(sec: any, ei: number, v: any): Tol {
  const cfg = sec.elements[ei] || {};
  return sec.mode === 'thk' ? tolThk(v, cfg.s || 0) : tolHb(v, cfg.lo ?? sec.lo, cfg.hi ?? sec.hi);
}

export function secTolList(sec: any, d: any): Tol[] {
  const f: Tol[] = (sec.fields || []).filter((x: any) => x.tol).map((x: any) => tolField(x.tol, d.values?.[x.key]) as Tol);
  if (sec.kind === 'checklist') return sec.items.map(([code, , opts]: any) => { const i = d.items?.[code]; return i >= 0 && opts[i] ? opts[i][1] : 'empty'; });
  if (sec.kind === 'points') return (d.elements || []).flatMap((el: any, ei: number) => el.points.map((p: any) => pointTol(sec, ei, p.value)));
  if (sec.kind === 'table') return [...(d.rows || []).map((r: any) => tolRow(sec.tol, r)), ...f];
  return f;
}

export type SecStatus = 'not_started' | 'in_progress' | 'done' | 'skipped';

export function secStatus(sec: any, d: any): SecStatus {
  if (sec.kind === 'info') return 'done';
  if (d.np) return 'skipped';
  let total = 0;
  let filled = 0;
  const need = (ok: boolean) => { total += 1; if (ok) filled += 1; };
  (sec.fields || []).filter((f: any) => f.req).forEach((f: any) => need(s(d.values?.[f.key]) !== ''));
  if (sec.kind === 'checklist') sec.items.forEach(([code]: any) => need((d.items?.[code] ?? -1) >= 0));
  if (sec.kind === 'points') (d.elements || []).forEach((el: any) => el.points.forEach((p: any) => { if (!p.extra || p.value) need(s(p.value) !== ''); }));
  if (sec.kind === 'table') {
    need((d.rows || []).length > 0);
    (d.rows || []).forEach((r: any) => sec.cols.forEach((c: any) => { if (!c.reqIf || s(r[c.reqIf.col]) === c.reqIf.eq) need(s(r[c.key]) !== ''); }));
  }
  if (sec.stage === 'ПЭ') need(s(d.concl) !== '');
  if (filled === 0) return 'not_started';
  return filled === total ? 'done' : 'in_progress';
}
