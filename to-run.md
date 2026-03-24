# STREAM MODE — real-time, you're watching charts
# Connects to live OANDA tick feed
# Fires alert the moment MSS/ChoCH prints on M1 close
# Dashboard live at http://localhost:5000
python main.py stream

# LIVE MODE — background polling every 5 min
# Good for when you're away or not actively watching
# Still sends Slack alerts for A/A+ setups
# Dashboard updates at http://localhost:5000
python main.py live

# SCAN MODE — one-time scan, good for testing
# Scans all 11 pairs once and exits
# No loop, no dashboard
python main.py scan


# Long trade
python main.py took GBP_JPY long

# Short trade
python main.py took NZD_JPY short

(forex-agent) ompandya@MacBookAir forex-agent % git log --oneline -1
244b7e0 (HEAD -> main) Latest update mar 23 8.48