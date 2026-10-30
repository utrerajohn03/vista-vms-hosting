// Page definitions. `d` is the key in the /api/state snapshot; `cust` names a custom page component.

export const RL = { admin: 'Admin', guard: 'Security guard', hoa: 'HOA office', household: 'Household account holder' };
export const START = { admin: 'dashboard', guard: 'g_gate', hoa: 'h_verify', household: 'u_req' };

// badge colour per status
export const BC = {
  Pending: 'a', 'Waiting at gate': 'a', 'In HOA queue': 'a', 'Awaiting HOA': 'a', Invited: 'a', Open: 'a', Queued: 'a', 'Not scanned': 'a', Unlinked: 'a',
  Inside: 'g', Arrived: 'g', Verified: 'g', Active: 'g', Available: 'g', Mapped: 'g', Sent: 'g',
  Issued: 'b',
  Declined: 'r', Rejected: 'r', Missing: 'r', 'Wrong destination': 'r', 'Red flag': 'r', Lost: 'r',
  Closed: 'n', Left: 'n', Resolved: 'n', Inactive: 'n',
};
export const BADGE = {
  a: 'border-amber-200 bg-amber-50 text-amber-700',
  b: 'border-blue-200 bg-blue-50 text-blue-700',
  g: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  r: 'border-rose-200 bg-rose-50 text-rose-700',
  n: 'border-gray-200 bg-gray-50 text-gray-700',
};

export const NAV = [
  ['Operations', [['dashboard', 'Dashboard', 'grid'], ['visits', 'Visits', 'clip']]],
  ['Setup', [['households', 'Households', 'house'], ['map', 'Village map and wayfinding', 'map'], ['gates', 'Gates and passes', 'gate'], ['staff', 'Guards and HOA office', 'people'], ['restricted', 'Restricted areas', 'shield']]],
  ['Monitoring', [['alerts', 'Alerts', 'bell'], ['messages', 'Messages', 'chat'], ['reports', 'Reports', 'bars'], ['audit', 'Audit log', 'book']]],
  ['', [['settings', 'Settings', 'gear']]],
];
export const NAVS = {
  admin: NAV,
  guard: [['Operations', [['g_gate', 'Gate', 'clip'], ['g_walk', 'Walk-in', 'user'], ['g_exit', 'Exit', 'gate'], ['g_notice', 'Notices', 'chat'], ['alerts', 'Alerts', 'bell']]]],
  hoa: [['Office', [['h_verify', 'Verify households', 'house'], ['h_queue', 'Unmatched queue', 'warn'], ['h_today', 'Today’s visits', 'clip']]]],
  household: [['My household', [['u_req', 'Visit requests', 'clip'], ['u_house', 'At the house', 'house'], ['u_form', 'Household form', 'book']]]],
};

// Walk-in: the same details as the visitor form, so the same checks can run at the gate (group names, declared vehicle).
const car = (v) => v.arr === 'Own vehicle';
const WF = [
  { k: 'visitor', l: 'Visitor name', r: 1 },
  { k: 'phone', l: 'Phone', ph: 'Optional' },
  { k: 'house', l: 'House number', r: 1, ph: 'e.g. B1-L4' },
  { k: 'host', l: 'Person visiting', ph: 'Blank = any household member' },
  { k: 'purpose', l: 'Purpose', ph: 'Optional' },
  { k: 'arr', l: 'Arriving by', t: 'select', o: ['Walking', 'Own vehicle', 'Ride'] },
  { k: 'kind', l: 'Vehicle type', ph: 'e.g. Sedan, SUV (optional)', show: car },
  { k: 'color', l: 'Vehicle color', ph: 'Optional', show: car },
  { k: 'plate', l: 'Plate number', ph: 'Optional', show: car },
  { k: 'friends', l: 'Friends with the visitor', t: 'textarea', ph: 'One name per line. Each gets their own pass.' },
];
const VCOLS = [['ref', 'Ref'], ['visitor', 'Visitor'], ['house', 'House'], ['host', 'Host'], ['arr', 'Arrival'], ['when', 'Time'], ['flag', 'Gate', 'b'], ['st', 'Status', 'b']];
const VC2 = [['ref', 'Ref'], ['visitor', 'Visitor'], ['house', 'House'], ['arr', 'Arrival'], ['tok', 'QR code'], ['flag', 'Gate', 'b'], ['st', 'Status', 'b']];
const INSIDE = ['Inside', 'Arrived'];

export const PG = {
  dashboard: { t: 'Dashboard', s: 'Today at Greenfield Village', cust: 'dash' },
  visits: {
    t: 'Visits', s: 'Approve, check in and track every visitor', d: 'visits', cols: VCOLS,
    acts: (r) => ({
      Pending: ['Approve', 'Decline', 'Edit'], 'Waiting at gate': ['Check in', 'Decline'],
      Inside: ['Mark arrived', 'Mark left', 'Flag wrong destination'], Arrived: ['Mark left'],
      Missing: ['Close with reason', 'Mark left'], 'In HOA queue': ['Reject', 'Edit'], 'Wrong destination': ['Close with reason'],
    }[r.st] || []),
    add: { l: 'New walk-in', f: WF, note: 'The guard calls the household. No pass until it approves.' },
    tabs: [
      { k: 'All visits' },
      { k: 'Waiting at gate', f: (r) => r.st === 'Waiting at gate' },
      { k: 'Inside', f: (r) => INSIDE.includes(r.st) },
      { k: 'HOA queue', f: (r) => r.st === 'In HOA queue' },
      { k: 'Exceptions', f: (r) => ['Missing', 'Wrong destination'].includes(r.st) },
    ],
  },
  households: {
    t: 'Households', s: 'Verify households before they can approve visits', d: 'households',
    cols: [['lot', 'Lot'], ['owner', 'Owner'], ['holder', 'Account holder'], ['people', 'People listed'], ['st', 'Status', 'b']],
    acts: (r) => (r.st === 'Verified' ? ['Edit', 'Copy sign-in link'] : r.st === 'Invited' ? ['Resend invitation', 'Copy sign-in link'] : ['Verify', 'Edit', 'Copy sign-in link']),
    add: { l: 'Invite household', f: [{ k: 'holder', l: 'Account holder email', t: 'email', r: 1 }] },
    tabs: [{ k: 'All' }, { k: 'Verified', f: (r) => r.st === 'Verified' }, { k: 'Awaiting verification', f: (r) => r.st === 'Awaiting HOA' }, { k: 'Invited', f: (r) => r.st === 'Invited' }],
  },
  map: {
    t: 'Village map and wayfinding', s: 'Import or draw the map, then mark blocks, lots, households and gates',
    tabs: [
      { k: 'Map editor', cust: 'mapEd', add: { l: 'Import map', f: [{ k: 'file', l: 'Map image or PDF', t: 'file' }], imp: 1 } },
      {
        k: 'Lots and households', d: 'lots', cols: [['lot', 'Lot'], ['household', 'Household'], ['people', 'People listed'], ['st', 'Status', 'b']], acts: () => ['Edit'],
        add: { l: 'Add lot', f: [{ k: 'lot', l: 'Lot code', r: 1, ph: 'e.g. B2-L3' }, { k: 'household', l: 'Household', ph: 'Owner name' }] },
      },
      { k: 'Wayfinding', d: 'routes', cols: [['dest', 'Destination'], ['route', 'Route from gate'], ['shown', 'Shown to visitor'], ['st', 'Status', 'b']], acts: () => ['Edit route'] },
    ],
  },
  gates: {
    t: 'Gates and passes', s: 'Gates, pass inventory, issue and return',
    tabs: [
      {
        k: 'Gates', d: 'gates', cols: [['name', 'Gate'], ['type', 'Used for'], ['st', 'Status', 'b']], acts: (r) => ['Edit', r.st === 'Active' ? 'Deactivate' : 'Activate'],
        add: { l: 'Add gate', f: [{ k: 'name', l: 'Gate name', r: 1 }, { k: 'type', l: 'Used for', t: 'select', o: ['Entry and exit', 'Deliveries', 'Walk-ins'] }] },
      },
      {
        k: 'Passes', d: 'passes', cols: [['no', 'Pass'], ['holder', 'Held by'], ['st', 'Status', 'b']], acts: (r) => (r.st === 'Lost' ? ['Mark found'] : r.st === 'Available' ? ['Mark lost'] : []),
        add: { l: 'Add pass', f: [{ k: 'no', l: 'Pass number', r: 1, ph: 'P09' }] },
      },
    ],
  },
  staff: {
    t: 'Guards and HOA office', s: 'Accounts for gate and office staff', d: 'staff',
    cols: [['name', 'Name'], ['email', 'Email'], ['role', 'Role'], ['st', 'Status', 'b']],
    acts: (r) => ['Edit', r.st === 'Active' ? 'Deactivate' : 'Activate'],
    add: { l: 'Add account', f: [{ k: 'name', l: 'Full name', r: 1 }, { k: 'email', l: 'Email', t: 'email', r: 1 }, { k: 'role', l: 'Role', t: 'select', o: ['Guard', 'HOA office'] },
      { k: 'password', l: 'First password (at least 10 characters)', t: 'password' }], note: 'The person signs in with this email and password and gets only the role chosen here. Without a password they cannot sign in yet; you can set one later under Edit.' },
    tabs: [{ k: 'Guards', f: (r) => r.role === 'Guard' }, { k: 'HOA office', f: (r) => r.role === 'HOA office' }],
  },
  restricted: {
    t: 'Restricted areas', s: 'Tied to household members. Never shown to visitors.',
    tabs: [
      {
        k: 'Areas', d: 'areas', cols: [['area', 'Area'], ['members', 'Tied members'], ['since', 'Since'], ['st', 'Status', 'b']], acts: () => ['Edit', 'Deactivate'],
        add: { l: 'New area', f: [{ k: 'area', l: 'Area name', r: 1 }, { k: 'members', l: 'Household members', ph: 'Names, comma separated' }] },
      },
      { k: 'Tied members', d: 'rm', cols: [['member', 'Member'], ['household', 'Household'], ['area', 'Area'], ['st', 'Status', 'b']], acts: () => ['Remove'] },
    ],
  },
  alerts: {
    t: 'Alerts', s: 'Missing, overstays, wrong destinations and vehicle issues', d: 'alerts', adv: 1,
    cols: [['time', 'Time'], ['type', 'Type'], ['detail', 'Detail'], ['st', 'Status', 'b']],
    acts: (r) => (r.st === 'Open' ? ['Resolve'] : []),
    tabs: [{ k: 'Open', f: (r) => r.st === 'Open' }, { k: 'Resolved', f: (r) => r.st === 'Resolved' }],
  },
  messages: {
    t: 'Messages', s: 'Emails and notices sent to households and visitors', d: 'msgs',
    cols: [['time', 'Time'], ['to', 'To'], ['subject', 'Subject'], ['st', 'Status', 'b']], acts: () => ['Resend'],
    tabs: [{ k: 'Sent', f: (r) => r.st === 'Sent' }, { k: 'Queued', f: (r) => r.st === 'Queued' }],
  },
  reports: { t: 'Reports', s: 'Visit volume, gate activity and exceptions', export: 1, cust: 'rep', tabs: [{ k: 'Visits' }, { k: 'Arrival method' }, { k: 'Exceptions' }] },
  audit: {
    t: 'Audit log', s: 'Every step is recorded', d: 'audit', fk: 'role', export: 1,
    cols: [['time', 'Time'], ['actor', 'Actor'], ['role', 'Role'], ['action', 'Action']],
    tabs: [{ k: 'All' }, ...['Guard', 'Household', 'HOA office', 'Admin', 'Super Admin'].map((x) => ({ k: x, f: (r) => r.role === x }))],
  },
  settings: { t: 'Settings', s: 'Village visit rules and notifications', cust: 'sett', tabs: [{ k: 'General' }, { k: 'Visit rules' }, { k: 'Notifications' }] },

  // guard
  g_gate: {
    t: 'Gate', s: 'Scan the QR or search by name or code, then check ID and vehicle', d: 'visits', cols: VC2, acts: () => [], scan: 'gate',
    main: (r) => (r.st === 'Waiting at gate' ? 'Check in' : ''),
    tabs: [{ k: 'Waiting at gate', f: (r) => r.st === 'Waiting at gate' }, { k: 'Inside', f: (r) => INSIDE.includes(r.st) }],
  },
  g_walk: {
    t: 'Walk-in', s: 'Same checks run. No pass is issued until the household approves by phone.', d: 'visits', f: (r) => r.w,
    cols: [['ref', 'Ref'], ['visitor', 'Visitor'], ['house', 'House'], ['host', 'Host'], ['call', 'Call household'], ['st', 'Status', 'b']],
    acts: (r) => (r.st === 'Pending' && r.w ? ['Declined by phone'] : []),
    main: (r) => (r.w && r.st === 'Pending' ? 'Approved by phone' : ''),
    add: { l: 'New walk-in', f: WF, note: 'The guard calls the household. No pass until it approves.' },
  },
  g_notice: {
    t: 'Notices', s: 'Arrivals at the house and Missing flags sent to the guard', d: 'msgs', fk: 'to',
    cols: [['time', 'Time'], ['subject', 'Notice'], ['to', 'To']],
  },
  g_exit: {
    t: 'Exit', s: 'Scan each pass out, confirm the vehicle left, then mark the visit Left', d: 'visits',
    f: (r) => ['Inside', 'Arrived', 'Missing', 'Wrong destination'].includes(r.st),
    cols: [['ref', 'Ref'], ['visitor', 'Visitor'], ['house', 'House'], ['arr', 'Arrival'], ['st', 'Status', 'b']],
    acts: () => ['Close with reason'], main: () => 'Scan out', scan: 'exit',
  },
  // HOA office
  h_verify: {
    t: 'Verify households', s: 'Households cannot approve visits until verified', d: 'households',
    cols: [['lot', 'Lot'], ['owner', 'Owner'], ['holder', 'Account holder'], ['people', 'People listed'], ['st', 'Status', 'b']],
    acts: () => [], main: (r) => (r.st === 'Awaiting HOA' ? 'Verify' : ''),
    tabs: [{ k: 'Awaiting verification', f: (r) => r.st === 'Awaiting HOA' }, { k: 'Verified', f: (r) => r.st === 'Verified' }, { k: 'All' }],
  },
  h_queue: {
    t: 'Unmatched queue', s: 'Correct the house or name and resend, or reject with a reason. The visitor always sees the same neutral reply.', d: 'visits',
    f: (r) => r.st === 'In HOA queue', cols: [['ref', 'Ref'], ['visitor', 'Visitor'], ['house', 'House typed'], ['host', 'Person typed'], ['when', 'Time'], ['st', 'Status', 'b']],
    acts: () => ['Reject'], main: () => 'Correct and resend',
  },
  h_today: { t: 'Today’s visits', s: 'Visits scheduled for today and visitors who entered today', d: 'visits', f: (r) => r.today, cols: VCOLS, acts: () => [] },
  // household
  u_req: {
    t: 'Visit requests', s: 'Approve or decline visits to your household. You see other adults’ visitors only for minors.', d: 'visits',
    cols: [['ref', 'Ref'], ['visitor', 'Visitor'], ['host', 'Person visiting'], ['arr', 'Arrival'], ['when', 'Time'], ['st', 'Status', 'b']],
    acts: (r) => (r.st === 'Pending' ? ['Decline', 'Not for me'] : []), main: (r) => (r.st === 'Pending' ? 'Approve' : ''),
    tabs: [{ k: 'Needs approval', f: (r) => r.st === 'Pending' }, { k: 'All visits' }],
  },
  u_house: {
    t: 'At the house', s: 'Scan a pass to confirm arrival. A pass for another household is flagged as a wrong destination.', d: 'scan',
    cols: [['person', 'Person'], ['pass', 'Pass'], ['visit', 'Visit'], ['st', 'Status', 'b']], acts: () => [], main: (r) => (r.st === 'Not scanned' ? 'Scan at house' : ''),
  },
  u_form: { t: 'Household form', s: 'The people living here are listed only. They have no accounts.', cust: 'hform' },
};
