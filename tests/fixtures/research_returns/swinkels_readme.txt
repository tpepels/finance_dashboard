This document accompanies the Excel spreadsheet to calculate monthly and annual US bond returns
starting in 1962. It describes the content of each column in the spreadsheet. Reference to the data
series is Swinkels (2023). For a more detailed description of the data, and a comparison with other
(commercially available) interest rate data sets, see Swinkels (2019).

Since the original research with monthly data for the US starting in 1962, I have extended the data set:

United States           1947

Germany                 1972

Japan                   1974

Australia               1969

Norway                  1921

Sweden                  1920

France                  1987

UK                      1970

Canada                  1986



Original 1962 sheet

Column A: End of month date

Column B: Data on the yield-to-maturity of a 10-year bond. This data is from Federal Reserve Economic
Data (https://fred.stlouisfed.org) and the variable name is DSG10.

Column C: Calculation of the modified duration (see Tuckman and Serrat (2012), Equation (4.45) on page
146).

Column D: Calculation of the convexity (see Tuckman and Serrat (2012), Equation (4.52) on page 150).

Column E: Calculation of the bond return (see Tuckman and Serrat (2012), Equation (4.21) on page 138).

Column F: Cumulative bond return

Column G: < empty >

Column H: End of year date

Column I: Cumulative bond return (sourced from column F)

Column J: Bond return per year
Improved 1947 sheet

Column A: End of month date

Column B: Data on the yield-to-maturity of a 10-year bond. Splice of Column C (1947-61) and D (1962-).

Column C: This par bond data is from McColloch and Kwon (1993). https://www.asc.ohio-
state.edu/mcculloch.2/ts/mcckwon/mccull.htm

Column D: This data is from Federal Reserve Economic Data (https://fred.stlouisfed.org): DSG10.

Column E: Total return bond formula using revaluation of the par bond assuming the new yield.

Column F: Cumulative bond return

Column G: < empty >

Column H: End of year date

Column I: Cumulative bond return (sourced from column F)

Column J: Bond return per year



The sheets for the other countries follow the “Improved US 1947” format.

For an overview of the public source data, see the sheet “Data Sources”.



References

McCulloch, J., and Kwon, H., 1993, "U.S. Term structure data, 1947-1991", Ohio State University Working
Paper #93-6.

Swinkels, L., 2023, “Historical Data: International monthly government bond returns”, Erasmus
University Rotterdam (EUR). Dataset. https://doi.org/10.25397/eur.8152748

Swinkels, L., 2019, “Treasury Bond Return Data Starting in 1962”, Data 4(3), 91.
https://doi.org/10.3390/data4030091

Tuckman, B., and Serrat A., 2012, Fixed Income Securities Tools for Today's Markets, 3rd edition, John
Wiley And Sons Ltd.
