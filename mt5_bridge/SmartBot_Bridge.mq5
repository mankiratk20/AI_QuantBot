//+------------------------------------------------------------------+
//|                                             SmartBot_Bridge.mq5   |
//|               AI Quant Trading Bot - MT5 Cloud WebRequest Bridge |
//|        Synchronizes MT5 account & orders with the Cloud Bot      |
//+------------------------------------------------------------------+
#property copyright "AI Quant Trading Bot"
#property link      "https://ai-quant-bot-8j49.onrender.com"
#property version   "2.20"
#property description "Connects your local MetaTrader 5 terminal to the Cloud Trading Bot via HTTP WebRequest."

//--- Inputs
input group "=== Cloud Server Settings ==="
input string BotServerURL    = "https://ai-quant-bot-8j49.onrender.com"; // Render Cloud Bot URL (No trailing slash)
input int    PollFreqSec     = 2;                                       // Sync Frequency (seconds)

input group "=== Trade Execution Settings ==="
input int    MagicNumber     = 987654;                                  // Magic Number for Bot Orders
input int    SlippagePts     = 30;                                      // Slippage in points
input bool   EnableVerboseLog= true;                                    // Print sync messages in Experts tab

//--- Global Variables
datetime lastSyncTime = 0;
bool     webRequestWarned = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("====================================================================");
   Print("🚀 AI Quant Bot Cloud Bridge EA Initializing...");
   Print("🌐 Target Server URL: ", BotServerURL);
   Print("⚙️ Polling Frequency: Every ", PollFreqSec, " seconds.");
   Print("⚠️ IMPORTANT REQUIREMENT: In MT5, go to:");
   Print("   Tools ➜ Options ➜ Expert Advisors ➜ Check 'Allow WebRequest for listed URL'");
   Print("   and add: ", BotServerURL);
   Print("====================================================================");

   // Set timer for periodic telemetry
   EventSetTimer(PollFreqSec);

   // Perform initial sync immediately
   SendTelemetry();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("🛑 SmartBot_Bridge EA detached from chart.");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   SendTelemetry();
}

//+------------------------------------------------------------------+
//| Syncs Account info & active positions with the Cloud Bot         |
//+------------------------------------------------------------------+
void SendTelemetry()
{
   long login        = AccountInfoInteger(ACCOUNT_LOGIN);
   string server     = AccountInfoString(ACCOUNT_SERVER);
   string company    = AccountInfoString(ACCOUNT_COMPANY);
   string currency   = AccountInfoString(ACCOUNT_CURRENCY);
   double balance    = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin     = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   long leverage     = AccountInfoInteger(ACCOUNT_LEVERAGE);

   // Collect open positions
   string posJson = "[";
   int totalPos = PositionsTotal();
   int count = 0;
   for(int i = 0; i < totalPos; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         string sym = PositionGetString(POSITION_SYMBOL);
         ENUM_POSITION_TYPE pType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double vol = PositionGetDouble(POSITION_VOLUME);
         double priceOpen = PositionGetDouble(POSITION_PRICE_OPEN);
         double priceCurr = PositionGetDouble(POSITION_PRICE_CURRENT);
         double sl = PositionGetDouble(POSITION_SL);
         double tp = PositionGetDouble(POSITION_TP);
         double profit = PositionGetDouble(POSITION_PROFIT);

         string dirStr = (pType == POSITION_TYPE_BUY) ? "BUY" : "SELL";

         if(count > 0) posJson += ",";
         posJson += StringFormat("{\"ticket\":\"%d\",\"symbol\":\"%s\",\"direction\":\"%s\",\"volume\":%.2f,\"entry_price\":%.5f,\"current_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"pnl\":%.2f}",
                                 ticket, sym, dirStr, vol, priceOpen, priceCurr, sl, tp, profit);
         count++;
      }
   }
   posJson += "]";

   // Build JSON payload
   string payload = StringFormat(
      "{\"login\":%d,\"server\":\"%s\",\"company\":\"%s\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"positions\":%s}",
      login, server, company, currency, balance, equity, margin, freeMargin, leverage, posJson
   );

   // Prepare HTTP POST request
   char postData[];
   StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(postData, ArraySize(postData) - 1); // remove null terminator

   char resultData[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nAccept: application/json\r\n";

   string syncUrl = BotServerURL + "/api/bridge/sync";

   ResetLastError();
   int httpStatus = WebRequest("POST", syncUrl, headers, 4000, postData, resultData, resultHeaders);

   if(httpStatus == -1)
   {
      int err = GetLastError();
      if(err == 4014) // ERR_WEBREQUEST_NOT_ALLOWED
      {
         if(!webRequestWarned)
         {
            Print("❌ WebRequest Error 4014: URL not allowed! Add '", BotServerURL, "' to MT5 ➜ Tools ➜ Options ➜ Expert Advisors ➜ Allow WebRequest for listed URL.");
            webRequestWarned = true;
         }
      }
      else
      {
         Print("⚠️ WebRequest failed with error: ", err, " to ", syncUrl);
      }
   }
   else if(httpStatus == 200)
   {
      webRequestWarned = false; // Reset warning on success
      string resStr = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);

      if(EnableVerboseLog)
      {
         PrintFormat("🟢 [SmartBot Bridge] Synced! Acc #%d (%s) | Balance: $%.2f | Equity: $%.2f", login, server, balance, equity);
      }

      // Check for incoming orders from cloud
      ProcessIncomingOrders(resStr);
   }
   else
   {
      PrintFormat("⚠️ Cloud server returned HTTP status %d: %s", httpStatus, CharArrayToString(resultData));
   }
}

//+------------------------------------------------------------------+
//| Parses and executes incoming orders from Cloud response          |
//+------------------------------------------------------------------+
void ProcessIncomingOrders(string jsonResponse)
{
   int ordersIdx = StringFind(jsonResponse, "\"orders\":[");
   if(ordersIdx < 0) return;

   int startBracket = ordersIdx + 9;
   int endBracket = StringFind(jsonResponse, "]", startBracket);
   if(endBracket <= startBracket + 1) return; // empty array "[]"

   string ordersStr = StringSubstr(jsonResponse, startBracket, endBracket - startBracket + 1);

   // Simple parser for queued order actions
   // Look for "action":"BUY" or "SELL"
   int actIdx = StringFind(ordersStr, "\"action\":\"");
   while(actIdx >= 0)
   {
      int actValStart = actIdx + 10;
      int actValEnd = StringFind(ordersStr, "\"", actValStart);
      string action = StringSubstr(ordersStr, actValStart, actValEnd - actValStart);

      // Extract symbol
      string symbol = _Symbol;
      int symIdx = StringFind(ordersStr, "\"symbol\":\"", actValEnd);
      if(symIdx >= 0)
      {
         int sStart = symIdx + 10;
         int sEnd = StringFind(ordersStr, "\"", sStart);
         symbol = StringSubstr(ordersStr, sStart, sEnd - sStart);
      }

      // Extract volume
      double volume = 0.10;
      int volIdx = StringFind(ordersStr, "\"volume\":", actValEnd);
      if(volIdx >= 0)
      {
         int vStart = volIdx + 9;
         int vEnd = StringFind(ordersStr, ",", vStart);
         if(vEnd < 0) vEnd = StringFind(ordersStr, "}", vStart);
         volume = StringToDouble(StringSubstr(ordersStr, vStart, vEnd - vStart));
      }

      // Extract sl, tp
      double sl = 0.0, tp = 0.0;
      int slIdx = StringFind(ordersStr, "\"sl\":", actValEnd);
      if(slIdx >= 0)
      {
         int slStart = slIdx + 5;
         int slEnd = StringFind(ordersStr, ",", slStart);
         sl = StringToDouble(StringSubstr(ordersStr, slStart, slEnd - slStart));
      }
      int tpIdx = StringFind(ordersStr, "\"tp\":", actValEnd);
      if(tpIdx >= 0)
      {
         int tpStart = tpIdx + 5;
         int tpEnd = StringFind(ordersStr, ",", tpStart);
         tp = StringToDouble(StringSubstr(ordersStr, tpStart, tpEnd - tpStart));
      }

      // Execute order
      ENUM_ORDER_TYPE oType = (action == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double price = (oType == ORDER_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_ASK) : SymbolInfoDouble(symbol, SYMBOL_BID);

      PrintFormat("⚡ [SmartBot Bridge] Executing %s order: %.2f lots of %s at %.5f (SL: %.5f, TP: %.5f)", action, volume, symbol, price, sl, tp);
      ExecuteDeal(symbol, oType, volume, price, sl, tp, "AI QuantBot Cloud");

      // Next order in list
      actIdx = StringFind(ordersStr, "\"action\":\"", actValEnd + 1);
   }
}

//+------------------------------------------------------------------+
//| Sends trade deal order to broker                                 |
//+------------------------------------------------------------------+
bool ExecuteDeal(string symbol, ENUM_ORDER_TYPE orderType, double volume, double price, double sl, double tp, string comment)
{
   MqlTradeRequest request;
   MqlTradeResult  result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action       = TRADE_ACTION_DEAL;
   request.symbol       = symbol;
   request.volume       = volume;
   request.type         = orderType;
   request.price        = price;
   request.sl           = sl;
   request.tp           = tp;
   request.deviation    = SlippagePts;
   request.magic        = MagicNumber;
   request.comment      = comment;
   request.type_filling = ORDER_FILLING_IOC;

   bool res = OrderSend(request, result);
   if(res && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
   {
      PrintFormat("✅ Trade executed successfully! Ticket #%d, Deal #%d", result.order, result.deal);
      return true;
   }
   else
   {
      PrintFormat("❌ Order failed: %s (Retcode: %d)", result.comment, result.retcode);
      return false;
   }
}
//+------------------------------------------------------------------+
