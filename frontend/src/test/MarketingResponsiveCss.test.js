// @vitest-environment node
import fs from 'node:fs'
import { describe, expect, it } from 'vitest'

const styles = fs.readFileSync('src/features/marketing/styles/marketing.pages.css', 'utf8')

describe('marketing responsive layout', () => {
  it('keeps the people cards stacked until the desktop layout', () => {
    expect(styles).not.toMatch(
      /@media \(min-width: 640px\) \{[\s\S]*?\.cronos-people__gallery\s*\{[^}]*repeat\(2, 1fr\)/,
    )
    expect(styles).toMatch(
      /@media \(min-width: 900px\) \{[\s\S]*?\.cronos-people__gallery\s*\{[^}]*repeat\(3, 1fr\)/,
    )
  })

  it('uses the compact workflow graphic throughout the single-column layout', () => {
    expect(styles).toMatch(
      /@media \(max-width: 899px\) \{[\s\S]*?\.cronos-workflow-visual__blocks\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)/,
    )
  })

  it('keeps workflow tabs stacked until the desktop layout', () => {
    expect(styles).not.toMatch(
      /@media \(min-width: 768px\) \{(?:(?!@media)[\s\S])*?\.cronos-tabs\s*\{[^}]*repeat\(3, 1fr\)/,
    )
    expect(styles).toMatch(
      /@media \(min-width: 900px\) \{[\s\S]*?\.cronos-tabs\s*\{[^}]*repeat\(3, 1fr\)/,
    )
  })
})
