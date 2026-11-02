// Dated, documented reference markers, never modifications of recorded data.
// No event is asserted to cause a particular economic series to move.
export interface HistoryEvent {
  date: string;
  title: string;
  source: string;
  description: string;
}
export const HISTORY_EVENTS: HistoryEvent[] = [
  {
    date: '1999-01-01',
    title: 'Euro introduced',
    description: 'Start of the euro as an accounting currency.',
    source: 'https://www.ecb.europa.eu/euro/intro/html/index.en.html',
  },
  {
    date: '2008-09-15',
    title: 'Lehman Brothers bankruptcy',
    description: 'Lehman Brothers filed for bankruptcy protection.',
    source: 'https://www.federalreservehistory.org/essays/lehman-brothers-collapse',
  },
  {
    date: '2020-03-11',
    title: 'WHO pandemic assessment',
    description: 'WHO characterized COVID-19 as a pandemic.',
    source: 'https://www.who.int/europe/emergencies/situations/covid-19',
  },
];
