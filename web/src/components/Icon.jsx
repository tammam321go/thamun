const PATHS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10',
  pay: 'M4 12h14m0 0-5-5m5 5-5 5',
  review: 'M12 3a9 9 0 1 0 9 9h-9V3Z M15 3.5A9 9 0 0 1 20.5 9H15V3.5Z',
  goals: 'M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  ask: 'M4 5h16v11H9l-5 4V5Z',
  send_money: 'M4 12h14m0 0-5-5m5 5-5 5',
  cash_out: 'M12 4v12m0 0-5-5m5 5 5-5M5 20h14',
  merchant_payment: 'M4 9h16l-1.5 10h-13L4 9Zm3 0 2-5h6l2 5',
  bill_payment: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6M9 12h6',
  mobile_recharge: 'M8 2h8v20H8V2Zm3 16h2',
  verify: 'M12 3l7 3v5c0 4.6-3 8.4-7 10-4-1.6-7-5.4-7-10V6l7-3Zm-3 9 2.2 2.2L15.5 10',
  flag: 'M6 21V4m0 1h11l-2 4 2 4H6',
  close: 'M6 6l12 12M18 6 6 18',
  check: 'M5 12.5 10 17l9-10',
}

export default function Icon({ name, size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.pay} />
    </svg>
  )
}
