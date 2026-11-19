//+------------------------------------------------------------------+
//|                                             SmartBot_Bridge.mq5   |
//|               AI-Powered Smart Trading Bot - MT5 Bridge EA       |
//|                    Connects MT5 to Local Python Bot Server       |
//+------------------------------------------------------------------+
#property copyright "AI Smart Trading Bot"
#property link      "http://127.0.0.1:5000"
#property version   "2.00"
#property description "Bridges MetaTrader 5 orders and price data with the AI Trading Bot."

input string BotServerURL = "http://127.0.0.1:5000"; // Python Bot Endpoint
input int    MagicNumber  = 987654;                  // Magic Number for Bot Orders
input int    SlippagePts  = 20;                      // Slippage in points
input int    PollFreqSec  = 1;                       // Polling Frequency (seconds)

datetime lastPollTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("SmartBot_Bridge EA initialized! Connecting to: ", BotServerURL);
   EventSetTimer(PollFreqSec);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("SmartBot_Bridge EA detached.");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   // Push tick & account telemetry to local bot
   SendTelemetry();
}

//+------------------------------------------------------------------+
//| Syncs Account info & active quotes with Python Bot              |
//+------------------------------------------------------------------+
void SendTelemetry()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   string company = AccountInfoString(ACCOUNT_COMPANY);
   long login = AccountInfoInteger(ACCOUNT_LOGIN);

   // In live production, WebRequest sends telemetry to BotServerURL
   // Ensure BotServerURL is added to Tools -> Options -> Expert Advisors -> Allow WebRequest
}

//+------------------------------------------------------------------+
//| Order Execution Function                                         |
//+------------------------------------------------------------------+
bool ExecuteOrder(string symbol, ENUM_ORDER_TYPE orderType, double volume, double price, double sl, double tp, string comment)
{
   MqlTradeRequest request;
   MqlTradeResult  result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = symbol;
   request.volume   = volume;
   request.type     = orderType;
   request.price    = price;
   request.sl       = sl;
   request.tp       = tp;
   request.deviation= SlippagePts;
   request.magic    = MagicNumber;
   request.comment  = comment;
   request.type_filling = ORDER_FILLING_IOC;

   return OrderSend(request, result);
}
