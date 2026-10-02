export const PALETTE = ['#0F4C5C', '#D48A1E', '#B5473A', '#5B8C5A', '#4A6FA5', '#7D4E7B', '#9AA7AB']

export default function Donut({ slices, centre, caption }) {
  const total = slices.reduce((sum, s) => sum + s.amount, 0) || 1
  const radius = 54
  const length = 2 * Math.PI * radius
  let offset = 0
  return (
    <svg className="donut" viewBox="0 0 140 140" role="img" aria-label={caption}>
      <circle cx="70" cy="70" r={radius} fill="none" stroke="var(--line)" strokeWidth="20" />
      {slices.map((s, i) => {
        const part = (s.amount / total) * length
        const gap = slices.length > 1 ? 1.5 : 0
        const el = (
          <circle key={s.name} cx="70" cy="70" r={radius} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth="20"
            strokeDasharray={`${Math.max(part - gap, 0)} ${length - Math.max(part - gap, 0)}`} strokeDashoffset={-offset}
            transform="rotate(-90 70 70)" />
        )
        offset += part
        return el
      })}
      <text x="70" y="67" textAnchor="middle" className="donut-value">{centre}</text>
      <text x="70" y="84" textAnchor="middle" className="donut-caption">{caption}</text>
    </svg>
  )
}
