export interface Currency {
  code: string
  symbol: string
}

export const CURRENCIES: Currency[] = [
  { code: 'EUR', symbol: '€' },
  { code: 'CHF', symbol: 'CHF' },
  { code: 'USD', symbol: '$' },
  { code: 'GBP', symbol: '£' },
  { code: 'SEK', symbol: 'kr' },
  { code: 'DKK', symbol: 'kr' },
  { code: 'NOK', symbol: 'kr' },
  { code: 'PLN', symbol: 'zł' },
]
