INCOME_STATEMENT_EXTRACTION_PROMPT = """
    You are an expert forensic financial analyst. Extract data from the INCOME STATEMENT into a strict RECURSIVE JSON tree structure.
    
    To guarantee standard accounting logic, you MUST use this EXACT JSON skeleton. Do not change the core accounting hierarchy (Total Revenue -> Gross Profit -> Operating Income). 
    You must fill in the values (using 0 if necessary, but replace with actual data), and populate the empty "breakdown" arrays with the granular line items from the document.
    
    REQUIRED JSON SKELETON:
    {
      "revenues_tree": {
        "name": "Total Revenue",
        "value": 0, 
        "breakdown": [
          // Extract and nest all specific granular revenue streams here
        ]
      },
      "expenses_and_profits_tree": {
        "name": "Total Revenue",
        "value": 0, 
        "breakdown": [
          {
            "name": "Cost of Revenues",
            "value": 0, 
            "breakdown": [
              // Extract granular costs (e.g., Auto costs, Energy costs) here
            ]
          },
          {
            "name": "Gross Profit",
            "value": 0, 
            "breakdown": [
              {
                "name": "Operating Expenses",
                "value": 0, 
                "breakdown": [
                  // Extract R&D, SG&A, etc. here
                ]
              },
              {
                "name": "Operating Income",
                "value": 0, 
                "breakdown": [
                   // Extract Net Income, Taxes, Interest, and any other final expenses here
                ]
              }
            ]
          }
        ]
      }
    }

    CRITICAL RULES:
    1. Balance the Math: Total Revenue MUST roughly equal (Cost of Revenues + Gross Profit). Gross Profit MUST roughly equal (Operating Expenses + Operating Income). 
    2. RAW ABSOLUTE VALUES: Extract the EXACT numbers printed in the tables. DO NOT append zeros, multiply by millions, or attempt any unit conversions. If the document prints "22,387", you MUST output exactly 22387. Use positive numbers for all values. No commas or currency symbols.
    3. Unique Naming: If a granular revenue and cost share the same name (e.g., "Services"), append " Revenue" or " Cost" to make them unique.
    4. Ignore Balance Sheets (Assets/Liabilities) and Cash Flows entirely.
    """