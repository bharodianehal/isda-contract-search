"""Counterparty reference data for the 20 synthetic ISDA agreements.

Each entry drives the party-specific, *searchable* variation that a legal
analyst would actually query on: governing law, base currency, threshold
amounts, Automatic Early Termination election, additional termination events,
covered product set, Specified Entities, etc. The printed Master Agreement
boilerplate is identical across all agreements (as in real practice); the
Schedule and Credit Support Annex carry the differentiation.
"""

# Party A is constant across the book (our institution).
PARTY_A = {
    "name": "Databricks Capital Markets LLC",
    "short": "Party A",
    "jurisdiction": "Delaware, United States",
    "office": "New York",
    "lei": "549300DBRXCAPMKTS001",
}

# 20 financial-services counterparties. product_set and clause elections are
# deliberately varied so that keyword searches return differentiated subsets.
COUNTERPARTIES = [
    {
        "id": "CP01", "name": "State Street Bank and Trust Company",
        "short": "State Street", "type": "Custodian Bank",
        "jurisdiction": "Massachusetts, United States", "office": "Boston",
        "lei": "571474TGEMMWANRLN572", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 10,000,000", "mta": "USD 250,000",
        "independent_amount": "USD 5,000,000", "cross_default": "USD 50,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards", "Cross-Currency Swaps"],
        "specified_entity": "any Affiliate", "ate": [
            "Ratings Downgrade below BBB- (S&P) or Baa3 (Moody's)"],
        "effective": "2019-03-15",
    },
    {
        "id": "CP02", "name": "The Bank of New York Mellon",
        "short": "BNY Mellon", "type": "Custodian Bank",
        "jurisdiction": "New York, United States", "office": "New York",
        "lei": "HPFHU0OQ28E4N0NFVK49", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 15,000,000", "mta": "USD 500,000",
        "independent_amount": "None", "cross_default": "USD 75,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "Repo Transactions", "Securities Lending"],
        "specified_entity": "any Affiliate", "ate": [
            "Net Asset Value Decline of 20% over any calendar month"],
        "effective": "2018-07-01",
    },
    {
        "id": "CP03", "name": "Goldman Sachs International",
        "short": "Goldman Sachs", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "W22LROWP2IHZNBB6K528", "governing_law": "English",
        "base_ccy": "EUR", "threshold": "EUR 20,000,000", "mta": "EUR 500,000",
        "independent_amount": "EUR 10,000,000", "cross_default": "EUR 100,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Credit Default Swaps", "Equity Swaps",
                     "FX Options", "Commodity Swaps"],
        "specified_entity": "Goldman Sachs Group, Inc.", "ate": [
            "Key Person Event", "Ratings Downgrade below A- (S&P)"],
        "effective": "2020-01-20",
    },
    {
        "id": "CP04", "name": "Morgan Stanley & Co. International plc",
        "short": "Morgan Stanley", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "4PQUHN3JPFGFNF3BB653", "governing_law": "English",
        "base_ccy": "USD", "threshold": "USD 25,000,000", "mta": "USD 500,000",
        "independent_amount": "USD 15,000,000", "cross_default": "USD 100,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Credit Default Swaps", "Equity Swaps",
                     "Total Return Swaps", "FX Forwards"],
        "specified_entity": "Morgan Stanley (parent)", "ate": [
            "Ratings Downgrade below BBB (S&P)", "Illegality of Specified Transaction"],
        "effective": "2019-11-05",
    },
    {
        "id": "CP05", "name": "JPMorgan Chase Bank, National Association",
        "short": "JPMorgan", "type": "Dealer",
        "jurisdiction": "New York, United States", "office": "New York",
        "lei": "7H6GLXDRUGQFU57RNE97", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 30,000,000", "mta": "USD 1,000,000",
        "independent_amount": "None", "cross_default": "USD 150,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards", "Cross-Currency Swaps",
                     "Commodity Swaps", "Credit Default Swaps"],
        "specified_entity": "JPMorgan Chase & Co.", "ate": [
            "Ratings Downgrade below A3 (Moody's)"],
        "effective": "2017-05-12",
    },
    {
        "id": "CP06", "name": "Citibank, N.A.",
        "short": "Citibank", "type": "Dealer",
        "jurisdiction": "New York, United States", "office": "New York",
        "lei": "E57ODZWZ7FF32TWEFA76", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 20,000,000", "mta": "USD 500,000",
        "independent_amount": "USD 8,000,000", "cross_default": "USD 100,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Options", "Emerging Markets Swaps"],
        "specified_entity": "Citigroup Inc.", "ate": [
            "Ratings Downgrade below BBB- (S&P)"],
        "effective": "2018-02-28",
    },
    {
        "id": "CP07", "name": "Bank of America, N.A.",
        "short": "Bank of America", "type": "Dealer",
        "jurisdiction": "North Carolina, United States", "office": "Charlotte",
        "lei": "B4TYDEB6GKMZO031MB27", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 25,000,000", "mta": "USD 500,000",
        "independent_amount": "None", "cross_default": "USD 125,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards", "Municipal Swaps"],
        "specified_entity": "Bank of America Corporation", "ate": [
            "Ratings Downgrade below Baa2 (Moody's)"],
        "effective": "2019-06-18",
    },
    {
        "id": "CP08", "name": "Wells Fargo Bank, N.A.",
        "short": "Wells Fargo", "type": "Dealer",
        "jurisdiction": "South Dakota, United States", "office": "San Francisco",
        "lei": "KB1H1DSPRFMYMCUFXT09", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 15,000,000", "mta": "USD 250,000",
        "independent_amount": "None", "cross_default": "USD 75,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards"],
        "specified_entity": "Wells Fargo & Company", "ate": [
            "Ratings Downgrade below BBB (S&P)"],
        "effective": "2020-09-30",
    },
    {
        "id": "CP09", "name": "Deutsche Bank AG",
        "short": "Deutsche Bank", "type": "Dealer",
        "jurisdiction": "Federal Republic of Germany", "office": "Frankfurt",
        "lei": "7LTWFZYICNSX8D621K86", "governing_law": "English",
        "base_ccy": "EUR", "threshold": "EUR 15,000,000", "mta": "EUR 500,000",
        "independent_amount": "EUR 12,000,000", "cross_default": "EUR 100,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Credit Default Swaps", "FX Options",
                     "Structured Notes"],
        "specified_entity": "any Affiliate", "ate": [
            "Ratings Downgrade below BBB- (S&P)", "Bail-in / Resolution Event"],
        "effective": "2018-04-10",
    },
    {
        "id": "CP10", "name": "Barclays Bank PLC",
        "short": "Barclays", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "G5GSEF7VJP5I7OUK5573", "governing_law": "English",
        "base_ccy": "GBP", "threshold": "GBP 10,000,000", "mta": "GBP 250,000",
        "independent_amount": "GBP 5,000,000", "cross_default": "GBP 75,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Inflation Swaps", "Credit Default Swaps",
                     "Equity Options"],
        "specified_entity": "Barclays PLC", "ate": [
            "Ratings Downgrade below A- (S&P)", "Bail-in / Resolution Event"],
        "effective": "2019-08-22",
    },
    {
        "id": "CP11", "name": "BNP Paribas S.A.",
        "short": "BNP Paribas", "type": "Dealer",
        "jurisdiction": "French Republic", "office": "Paris",
        "lei": "R0MUWSFPU8MPRO8K5P83", "governing_law": "English",
        "base_ccy": "EUR", "threshold": "EUR 18,000,000", "mta": "EUR 500,000",
        "independent_amount": "EUR 9,000,000", "cross_default": "EUR 90,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "FX Forwards", "Commodity Swaps",
                     "Credit Default Swaps"],
        "specified_entity": "any Affiliate", "ate": [
            "Ratings Downgrade below BBB (S&P)", "Bail-in / Resolution Event"],
        "effective": "2020-03-11",
    },
    {
        "id": "CP12", "name": "Credit Suisse International",
        "short": "Credit Suisse", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "E58DKGMJYYYJLN8C3868", "governing_law": "English",
        "base_ccy": "CHF", "threshold": "CHF 12,000,000", "mta": "CHF 250,000",
        "independent_amount": "CHF 6,000,000", "cross_default": "CHF 60,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Structured Notes", "Equity Swaps"],
        "specified_entity": "Credit Suisse Group AG", "ate": [
            "Ratings Downgrade below BBB- (S&P)", "Merger Without Assumption",
            "Bail-in / Resolution Event"],
        "effective": "2017-10-03",
    },
    {
        "id": "CP13", "name": "UBS AG",
        "short": "UBS", "type": "Dealer",
        "jurisdiction": "Switzerland", "office": "Zurich",
        "lei": "BFM8T61CT2L1QCEMIK50", "governing_law": "English",
        "base_ccy": "CHF", "threshold": "CHF 15,000,000", "mta": "CHF 250,000",
        "independent_amount": "CHF 7,500,000", "cross_default": "CHF 75,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "FX Options", "Equity Swaps",
                     "Structured Notes"],
        "specified_entity": "UBS Group AG", "ate": [
            "Ratings Downgrade below A- (S&P)", "Bail-in / Resolution Event"],
        "effective": "2018-12-14",
    },
    {
        "id": "CP14", "name": "HSBC Bank plc",
        "short": "HSBC", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "MP6I5ZYZBEU3UXPYFY54", "governing_law": "English",
        "base_ccy": "GBP", "threshold": "GBP 12,000,000", "mta": "GBP 250,000",
        "independent_amount": "None", "cross_default": "GBP 80,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "FX Forwards", "Emerging Markets Swaps",
                     "Commodity Swaps"],
        "specified_entity": "HSBC Holdings plc", "ate": [
            "Ratings Downgrade below BBB (S&P)"],
        "effective": "2019-01-28",
    },
    {
        "id": "CP15", "name": "Nomura International plc",
        "short": "Nomura", "type": "Dealer",
        "jurisdiction": "England and Wales", "office": "London",
        "lei": "DGQCSV2PHVF7I2743539", "governing_law": "English",
        "base_ccy": "JPY", "threshold": "JPY 1,500,000,000", "mta": "JPY 25,000,000",
        "independent_amount": "JPY 750,000,000", "cross_default": "JPY 7,500,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Cross-Currency Swaps", "Equity Swaps"],
        "specified_entity": "Nomura Holdings, Inc.", "ate": [
            "Ratings Downgrade below BBB- (S&P)"],
        "effective": "2020-06-08",
    },
    {
        "id": "CP16", "name": "Societe Generale S.A.",
        "short": "Societe Generale", "type": "Dealer",
        "jurisdiction": "French Republic", "office": "Paris",
        "lei": "O2RNE8IBXP4R0TD8PU41", "governing_law": "English",
        "base_ccy": "EUR", "threshold": "EUR 16,000,000", "mta": "EUR 500,000",
        "independent_amount": "EUR 8,000,000", "cross_default": "EUR 80,000,000",
        "aet": True, "csa_type": "English Law VM CSA (Transfer - Title Transfer)",
        "products": ["Interest Rate Swaps", "Equity Swaps", "Commodity Swaps",
                     "FX Forwards"],
        "specified_entity": "any Affiliate", "ate": [
            "Ratings Downgrade below BBB (S&P)", "Bail-in / Resolution Event"],
        "effective": "2018-09-19",
    },
    {
        "id": "CP17", "name": "Royal Bank of Canada",
        "short": "RBC", "type": "Dealer",
        "jurisdiction": "Canada", "office": "Toronto",
        "lei": "ES7IP3U3RHIGC71XBU11", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 20,000,000", "mta": "USD 500,000",
        "independent_amount": "None", "cross_default": "USD 100,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards", "Cross-Currency Swaps"],
        "specified_entity": "any Affiliate", "ate": [
            "Ratings Downgrade below A- (S&P)"],
        "effective": "2019-04-25",
    },
    {
        "id": "CP18", "name": "The Northern Trust Company",
        "short": "Northern Trust", "type": "Custodian Bank",
        "jurisdiction": "Illinois, United States", "office": "Chicago",
        "lei": "6PTKHDJ8HDUF78PFWH30", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 10,000,000", "mta": "USD 250,000",
        "independent_amount": "None", "cross_default": "USD 50,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "FX Forwards", "Securities Lending"],
        "specified_entity": "Northern Trust Corporation", "ate": [
            "Net Asset Value Decline of 25% over any calendar quarter"],
        "effective": "2020-11-16",
    },
    {
        "id": "CP19", "name": "BlackRock Financial Management, Inc.",
        "short": "BlackRock", "type": "Asset Manager",
        "jurisdiction": "New York, United States", "office": "New York",
        "lei": "549300LILU3UZWDAHOD8", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 5,000,000", "mta": "USD 100,000",
        "independent_amount": "USD 20,000,000", "cross_default": "USD 25,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "Credit Default Swaps", "Total Return Swaps",
                     "FX Forwards"],
        "specified_entity": "the relevant Fund only (no Affiliate)", "ate": [
            "Net Asset Value Decline of 15% over any calendar month",
            "Key Person Event", "Investment Manager Termination"],
        "effective": "2021-02-09",
    },
    {
        "id": "CP20", "name": "Pacific Investment Management Company LLC",
        "short": "PIMCO", "type": "Asset Manager",
        "jurisdiction": "Delaware, United States", "office": "Newport Beach",
        "lei": "549300DBELKF6PC7O737", "governing_law": "New York",
        "base_ccy": "USD", "threshold": "USD 5,000,000", "mta": "USD 100,000",
        "independent_amount": "USD 25,000,000", "cross_default": "USD 25,000,000",
        "aet": False, "csa_type": "New York Law VM CSA",
        "products": ["Interest Rate Swaps", "Credit Default Swaps", "TBA Transactions",
                     "FX Forwards", "Inflation Swaps"],
        "specified_entity": "the relevant Account only (no Affiliate)", "ate": [
            "Net Asset Value Decline of 15% over any calendar month",
            "Investment Manager Termination"],
        "effective": "2021-05-24",
    },
]

assert len(COUNTERPARTIES) == 20, "expected 20 counterparties"
