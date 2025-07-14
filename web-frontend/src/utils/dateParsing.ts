import { DateRange } from "@/types/scheduling";
import { ERROR_SHOULD_NOT_HAPPEN } from "@/constants/errors";

export function dateStrToDate(dateStr: string, dateRange: DateRange): Date {
  // Parse the item.id back to a Date, inferring year/month if needed.
  // Use dateRange to infer missing year/month if needed.
  // If id is YYYY-MM-DD, parse directly.
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return new Date(dateStr);
  }
  // If id is MM-DD, infer year from dateRange.startDate
  if (/^\d{2}-\d{2}$/.test(dateStr)) {
    const yyyy = new Date(dateRange.startDate!).getFullYear().toString().padStart(4, '0');
    const [mm, dd] = dateStr.split('-');
    return new Date(`${yyyy}-${mm}-${dd}`);
  }
  // If id is DD, infer month and year from dateRange.startDate
  if (/^\d{2}$/.test(dateStr)) {
    const yyyy = new Date(dateRange.startDate!).getFullYear().toString().padStart(4, '0');
    const mm = (new Date(dateRange.startDate!).getMonth() + 1).toString().padStart(2, '0');
    const dd = dateStr;
    return new Date(`${yyyy}-${mm}-${dd}`);
  }
  console.error(`Invalid date string: ${dateStr}. ${ERROR_SHOULD_NOT_HAPPEN}`);
  return new Date();
}
