import type { Field } from '~/types/metadata'
import type { Slot } from '~/types/uploads'

export function useMetadataParser() {
    function applyParsedMeta(slot: Slot, filename: string, schema: Field[]) {
        schema.forEach((f) => {
            if (f.extract_regex) {
                try {
                    const re = new RegExp(f.extract_regex, 'iu')
                    const m = filename.match(re)
                    if (m) {
                        let val = m[1] ?? m[0]

                        if (f.type === 'date' && m.groups) {
                            const { year, month, day } = m.groups
                            if (year && month && day) {
                                // Pad year to 4 digits (assume 20xx for 2-digit years)
                                const fullYear = year.length === 2 ? `20${year}` : year
                                val = `${fullYear}-${month}-${day}`
                            }
                        }

                        slot.values[f.key] = val
                    }
                } catch (e: any) {
                    console.error(`Invalid regex for metadata field ${f.key}: ${f.extract_regex}: ${e.message}`)
                }
            }
        })
    }

    return { applyParsedMeta }
}
