from server.schedule import ScheduleItem, GlobalSchedule, RoomSchedule

global_schedule = GlobalSchedule(file_path="schedule.csv")
squash_schedule = RoomSchedule(
    global_schedule=global_schedule,
    room_ids = [1, 2, 3],
    name = "Squash Courts",
    name_map = {
        1: "Squash 1",
        2: "Squash 2",
        3: "Squash 3"
    }
)
schedules = [squash_schedule]