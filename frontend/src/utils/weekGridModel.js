import { addDays, normalizeTimeLabel } from './formatUtils'

/**
 * Builds row/column data from the `/timeslots/range` days array.
 * Each entry is `{ date, version_id, effective_date, blocks }` and `blocks`
 * already contains only the blocks whose `day_of_week` matches that date.
 */
function buildDayGridModel(dayGrids) {
  const activeDays = []
  const uniqueTimes = new Set()
  const endTimeByDay = {}
  const versionByDay = {}
  const dayDateMap = {}

  dayGrids.forEach((entry) => {
    if (!entry?.blocks?.length) return
    const day = entry.blocks[0].day_of_week
    activeDays.push(day)
    dayDateMap[day] = entry.date
    versionByDay[day] = {
      versionId: entry.version_id ?? null,
      effectiveDate: entry.effective_date ?? null,
    }
    endTimeByDay[day] ??= {}
    entry.blocks.forEach((block) => {
      const start = normalizeTimeLabel(block.start_time)
      uniqueTimes.add(start)
      endTimeByDay[day][start] = normalizeTimeLabel(block.end_time)
    })
  })

  const sortedDays = [...new Set(activeDays)].sort((left, right) => left - right)
  const sortedTimes = [...uniqueTimes].sort((left, right) => left.localeCompare(right))
  const rowEndTime = Object.fromEntries(sortedTimes.map((start) => {
    const ends = sortedDays.map((day) => endTimeByDay[day]?.[start])
    const [first, ...rest] = ends
    const allDaysAgree = Boolean(first) && rest.every((end) => end === first)
    return [start, allDaysAgree ? first : null]
  }))

  return { activeDays: sortedDays, uniqueTimes: sortedTimes, endTimeByDay, versionByDay, dayDateMap, rowEndTime }
}

export function buildWeekGridModel(slots = [], baseTimeslots = [], weekStart = '', dayGrids = null) {
  const referenceTimeslots = baseTimeslots.length > 0
    ? baseTimeslots
    : slots.map((slot) => slot.timeslot).filter(Boolean)
  const uniqueTimes = [...new Set(referenceTimeslots.map((timeslot) => normalizeTimeLabel(timeslot.start_time)))]
    .sort((left, right) => left.localeCompare(right))
  const activeDays = [...new Set(referenceTimeslots.map((timeslot) => timeslot.day_of_week))]
    .sort((left, right) => left - right)
  const endTimeMap = Object.fromEntries(referenceTimeslots.map((timeslot) => [
    normalizeTimeLabel(timeslot.start_time),
    normalizeTimeLabel(timeslot.end_time),
  ]))
  const datesFromSlots = Object.fromEntries(slots
    .filter((slot) => slot.timeslot && slot.date)
    .map((slot) => [slot.timeslot.day_of_week, slot.date]))
  const dayDateMap = Object.fromEntries(activeDays.map((day) => [
    day,
    datesFromSlots[day] ?? (weekStart ? addDays(weekStart, day) : ''),
  ]))
  const slotMap = {}
  slots.forEach((slot) => {
    const key = `${slot.timeslot.day_of_week}:${normalizeTimeLabel(slot.timeslot.start_time)}`
    slotMap[key] ??= []
    slotMap[key].push(slot)
  })

  const model = { slotMap, uniqueTimes, activeDays, endTimeMap, dayDateMap }
  const hasDayGrids = Array.isArray(dayGrids) && dayGrids.length > 0
  if (!hasDayGrids) {
    return model
  }

  const dayModel = buildDayGridModel(dayGrids)
  const slotTimes = [...new Set(slots.map((slot) => normalizeTimeLabel(slot.timeslot.start_time)))]
  const slotDays = [...new Set(slots.map((slot) => slot.timeslot.day_of_week))]
  const slotEndByStart = Object.fromEntries(slots.map((slot) => [
    normalizeTimeLabel(slot.timeslot.start_time),
    normalizeTimeLabel(slot.timeslot.end_time),
  ]))
  const mergedTimes = [...new Set([...dayModel.uniqueTimes, ...slotTimes])]
    .sort((left, right) => left.localeCompare(right))
  const mergedDays = [...new Set([...dayModel.activeDays, ...slotDays])]
    .sort((left, right) => left - right)
  const mergedDates = Object.fromEntries(mergedDays.map((day) => [
    day,
    dayModel.dayDateMap[day]
      ?? datesFromSlots[day]
      ?? (weekStart ? addDays(weekStart, day) : ''),
  ]))
  const mergedRowEnd = Object.fromEntries(mergedTimes.map((start) => {
    const fromGrid = Object.prototype.hasOwnProperty.call(dayModel.rowEndTime, start)
    return [
      start,
      fromGrid
        ? dayModel.rowEndTime[start]
        : (endTimeMap[start] ?? slotEndByStart[start] ?? null),
    ]
  }))

  return {
    ...model,
    ...dayModel,
    activeDays: mergedDays,
    uniqueTimes: mergedTimes,
    dayDateMap: mergedDates,
    rowEndTime: mergedRowEnd,
  }
}
