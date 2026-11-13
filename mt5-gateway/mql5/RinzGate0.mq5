//+------------------------------------------------------------------+
//| RinzGate0.mq5 - Gate 0 reference EA (Rinz Algo, plan section 10.3)
//| Same rules as backend/app/strategies/reference.py (GATE0):
//|  - on the first tick of a new bar, look at the two last CLOSED bars
//|  - EMA(fast) crosses above EMA(slow) -> BUY at market; below -> SELL
//|  - SL / TP fixed in pips, measured from the signal bar's close
//|  - one position at a time, no other exit
//| Run it in the Strategy Tester ("1 minute OHLC"). When the test ends it
//| writes every closed trade to <Common>\Files\rinz_gate0_trades.csv,
//| which the Rinz Gate 0 page compares with the Rinz engine.
//+------------------------------------------------------------------+
#property copyright "Rinz Algo"
#property version   "1.00"
#property description "Gate 0 reference: EMA cross, fixed-pip SL/TP, fixed lots."

#include <Trade\Trade.mqh>

input int    FastEMA   = 20;
input int    SlowEMA   = 50;
input double SlPips    = 30;
input double TpPips    = 60;
input double Lots      = 0.10;
input int    PipPoints = 10;          // points per pip (5-digit FX, 3-digit JPY, 2-digit gold = 10)
input long   Magic     = 9000;
input string OutFile   = "rinz_gate0_trades.csv";

CTrade   trade;
int      hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE;
datetime lastBar = 0;

int OnInit()
  {
   hFast = iMA(_Symbol, PERIOD_CURRENT, FastEMA, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, PERIOD_CURRENT, SlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE)
      return(INIT_FAILED);
   trade.SetExpertMagicNumber(Magic);
   trade.SetDeviationInPoints(50);
   return(INIT_SUCCEEDED);
  }

bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionSelectByTicket(t) &&
         PositionGetInteger(POSITION_MAGIC) == Magic && PositionGetString(POSITION_SYMBOL) == _Symbol)
         return(true);
     }
   return(false);
  }

void OnTick()
  {
   datetime bar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bar == lastBar)
      return;
   lastBar = bar;
   double f[2], s[2];   // [0] = bar 2 (older), [1] = bar 1 (just closed)
   if(CopyBuffer(hFast, 0, 1, 2, f) != 2 || CopyBuffer(hSlow, 0, 1, 2, s) != 2)
      return;
   if(HasPosition())
      return;
   double pip = PipPoints * _Point;
   double c   = iClose(_Symbol, PERIOD_CURRENT, 1);
   if(f[0] <= s[0] && f[1] > s[1])
      trade.Buy(Lots, _Symbol, 0.0, NormalizeDouble(c - SlPips * pip, _Digits), NormalizeDouble(c + TpPips * pip, _Digits), "gate0");
   else if(f[0] >= s[0] && f[1] < s[1])
      trade.Sell(Lots, _Symbol, 0.0, NormalizeDouble(c + SlPips * pip, _Digits), NormalizeDouble(c - TpPips * pip, _Digits), "gate0");
  }

void OnDeinit(const int reason)
  {
   if(!HistorySelect(0, TimeCurrent() + 86400))
      return;
   int fh = FileOpen(OutFile, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE)
     {
      Print("RinzGate0: cannot write ", OutFile, " error ", GetLastError());
      return;
     }
   FileWrite(fh, "position_id", "side", "open_time", "open_price", "close_time", "close_price", "volume",
             "profit", "commission", "swap", "reason", "symbol", "timeframe", "fast", "slow", "sl_pips", "tp_pips");
   int n = HistoryDealsTotal();
   int rows = 0;
   for(int i = 0; i < n; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != Magic || HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;
      long pos = HistoryDealGetInteger(d, DEAL_POSITION_ID);
      ulong in = 0;
      for(int j = 0; j < n; j++)
        {
         ulong e = HistoryDealGetTicket(j);
         if(HistoryDealGetInteger(e, DEAL_POSITION_ID) == pos && HistoryDealGetInteger(e, DEAL_ENTRY) == DEAL_ENTRY_IN)
           { in = e; break; }
        }
      if(in == 0)
         continue;
      string side = HistoryDealGetInteger(in, DEAL_TYPE) == DEAL_TYPE_BUY ? "buy" : "sell";
      double commission = HistoryDealGetDouble(in, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      FileWrite(fh, pos, side,
                (long)HistoryDealGetInteger(in, DEAL_TIME), DoubleToString(HistoryDealGetDouble(in, DEAL_PRICE), _Digits),
                (long)HistoryDealGetInteger(d, DEAL_TIME), DoubleToString(HistoryDealGetDouble(d, DEAL_PRICE), _Digits),
                DoubleToString(HistoryDealGetDouble(in, DEAL_VOLUME), 2),
                DoubleToString(HistoryDealGetDouble(d, DEAL_PROFIT), 2), DoubleToString(commission, 2),
                DoubleToString(HistoryDealGetDouble(d, DEAL_SWAP), 2), (long)HistoryDealGetInteger(d, DEAL_REASON),
                _Symbol, EnumToString((ENUM_TIMEFRAMES)Period()), FastEMA, SlowEMA, SlPips, TpPips);
      rows++;
     }
   FileClose(fh);
   Print("RinzGate0: wrote ", rows, " trades to Common\\Files\\", OutFile);
  }
//+------------------------------------------------------------------+
