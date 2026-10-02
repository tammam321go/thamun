const MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_BN = ['জানুয়ারি', 'ফেব্রুয়ারি', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টেম্বর', 'অক্টোবর', 'নভেম্বর', 'ডিসেম্বর']

export function taka(value) {
  const n = Math.round(Number(value) || 0)
  return `৳${n.toLocaleString('en-US')}`
}

export function day(iso, lang = 'en') {
  if (!iso) return ''
  const [, m, d] = String(iso).slice(0, 10).split('-').map(Number)
  return `${d} ${(lang === 'bn' ? MONTHS_BN : MONTHS_EN)[m - 1]}`
}

export function monthName(key, lang = 'en') {
  const [y, m] = key.split('-').map(Number)
  return `${(lang === 'bn' ? MONTHS_BN : MONTHS_EN)[m - 1]} ${y}`
}

export function clock(iso) {
  return String(iso).slice(11, 16)
}

export function percent(value, digits = 0) {
  if (value === null || value === undefined) return 'n/a'
  return `${(value * 100).toFixed(digits)}%`
}
