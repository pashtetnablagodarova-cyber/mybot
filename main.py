import os
import staypresent

staypresent.cron(
    "https://ТВОЙ-АДРЕС.koyeb.app",
    interval=240,
)

staypresent.run(
    "bot.py",
    port=int(os.getenv("PORT", 8080)),
    restart_on_crash=True,
    max_restarts=5,
)
