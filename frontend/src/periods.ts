/** NBER peak-to-trough contraction months, not arbitrary crash windows.
 * They are explicitly US recession periods even on a world/Europe/Japan plot.
 * Per NBER, the peak month is the last month of expansion; recession begins
 * the next month and ends in the official trough month.
 * https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions
 */
export const NBER_CRISIS_WINDOWS = [
  { start: '2001-04-01', end: '2001-11-30' },
  { start: '2008-01-01', end: '2009-06-30' },
  { start: '2020-03-01', end: '2020-04-30' },
] as const;
export const NBER_SHADE_CAPTION =
  'Gray bands show NBER-dated US contractions around the dot-com crash, global financial crisis and COVID-19. These are not world or regional recession dates.';
