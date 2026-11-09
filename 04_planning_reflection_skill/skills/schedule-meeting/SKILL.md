---
name: schedule-meeting
description: Schedule a meeting in a virtual calendar, avoid occupied times, set a reminder, and verify the final calendar state.
---

# Schedule a meeting

Use this procedure when the user asks to create a calendar meeting with a reminder.

1. Read the current calendar and select an available slot within the user's constraints.
2. Create the meeting. If the slot became occupied, read the calendar again and make a new plan.
3. Set the requested reminder on the created meeting. If this step fails, keep the existing meeting and retry only the reminder when the error is transient.
4. Read the saved meeting and verify its time and reminder before reporting success.

The skill is a reusable procedure. It does not itself call the calendar tools or prove that the task succeeded.
