/**
 * Accessibility utilities and helpers for WCAG 2.1 AA compliance
 */

/**
 * Check color contrast ratio between two colors
 * @param foreground - Hex color (e.g., '#FFFFFF')
 * @param background - Hex color (e.g., '#000000')
 * @returns Contrast ratio (1-21)
 */
export function getContrastRatio(foreground: string, background: string): number {
  const lum1 = getLuminance(foreground);
  const lum2 = getLuminance(background);
  const brightest = Math.max(lum1, lum2);
  const darkest = Math.min(lum1, lum2);
  return (brightest + 0.05) / (darkest + 0.05);
}

/**
 * Calculate relative luminance of a color
 * @param hex - Hex color (e.g., '#FFFFFF')
 * @returns Luminance value (0-1)
 */
function getLuminance(hex: string): number {
  const rgb = hexToRgb(hex);
  const [r, g, b] = rgb.map((c) => {
    const sRGB = c / 255;
    return sRGB <= 0.03928 ? sRGB / 12.92 : Math.pow((sRGB + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Convert hex color to RGB array
 * @param hex - Hex color (e.g., '#FFFFFF' or '#FFF')
 * @returns RGB array [r, g, b]
 */
function hexToRgb(hex: string): number[] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) {
    // Handle shorthand hex (#FFF)
    const shorthand = /^#?([a-f\d])([a-f\d])([a-f\d])$/i.exec(hex);
    if (shorthand) {
      return [
        parseInt(shorthand[1] + shorthand[1], 16),
        parseInt(shorthand[2] + shorthand[2], 16),
        parseInt(shorthand[3] + shorthand[3], 16),
      ];
    }
    return [0, 0, 0];
  }
  return [
    parseInt(result[1], 16),
    parseInt(result[2], 16),
    parseInt(result[3], 16),
  ];
}

/**
 * Check if contrast ratio meets WCAG AA standards
 * @param ratio - Contrast ratio
 * @param level - 'AA' or 'AAA'
 * @param isLargeText - Whether text is 18pt+ or 14pt+ bold
 * @returns Whether contrast is sufficient
 */
export function meetsWCAGContrast(
  ratio: number,
  level: 'AA' | 'AAA' = 'AA',
  isLargeText: boolean = false
): boolean {
  if (level === 'AAA') {
    return isLargeText ? ratio >= 4.5 : ratio >= 7;
  }
  return isLargeText ? ratio >= 3 : ratio >= 4.5;
}

/**
 * Generate unique ID for ARIA attributes
 * @param prefix - ID prefix
 * @returns Unique ID string
 */
let idCounter = 0;
export function generateAriaId(prefix: string = 'aria'): string {
  return `${prefix}-${++idCounter}`;
}

/**
 * Accessibility audit result
 */
export interface AuditResult {
  component: string;
  issues: AuditIssue[];
  score: number; // 0-100
}

export interface AuditIssue {
  severity: 'critical' | 'serious' | 'moderate' | 'minor';
  wcag: string; // WCAG criterion (e.g., '1.1.1')
  description: string;
  element?: string;
  fix: string;
}

/**
 * Audit a component for accessibility issues
 * @param element - DOM element to audit
 * @param componentName - Component name for reporting
 * @returns Audit result
 */
export function auditElement(element: HTMLElement, componentName: string): AuditResult {
  const issues: AuditIssue[] = [];

  // Check images for alt text
  const images = element.querySelectorAll('img');
  images.forEach((img) => {
    if (!img.alt && !img.getAttribute('aria-hidden')) {
      issues.push({
        severity: 'critical',
        wcag: '1.1.1',
        description: 'Image missing alt text',
        element: img.outerHTML.slice(0, 100),
        fix: 'Add alt attribute describing image content',
      });
    }
  });

  // Check buttons for accessible names
  const buttons = element.querySelectorAll('button');
  buttons.forEach((button) => {
    const hasText = button.textContent?.trim();
    const hasAriaLabel = button.getAttribute('aria-label');
    const hasAriaLabelledBy = button.getAttribute('aria-labelledby');
    const hasTitle = button.title;

    if (!hasText && !hasAriaLabel && !hasAriaLabelledBy && !hasTitle) {
      issues.push({
        severity: 'critical',
        wcag: '4.1.2',
        description: 'Button missing accessible name',
        element: button.outerHTML.slice(0, 100),
        fix: 'Add text content, aria-label, or aria-labelledby',
      });
    }
  });

  // Check links for accessible names
  const links = element.querySelectorAll('a');
  links.forEach((link) => {
    const hasText = link.textContent?.trim();
    const hasAriaLabel = link.getAttribute('aria-label');
    const hasAriaLabelledBy = link.getAttribute('aria-labelledby');
    const hasTitle = link.title;

    if (!hasText && !hasAriaLabel && !hasAriaLabelledBy && !hasTitle) {
      issues.push({
        severity: 'critical',
        wcag: '4.1.2',
        description: 'Link missing accessible name',
        element: link.outerHTML.slice(0, 100),
        fix: 'Add text content, aria-label, or aria-labelledby',
      });
    }
  });

  // Check form inputs for labels
  const inputs = element.querySelectorAll('input, textarea, select');
  inputs.forEach((input) => {
    const id = input.id;
    const hasLabel = id && element.querySelector(`label[for="${id}"]`);
    const hasAriaLabel = input.getAttribute('aria-label');
    const hasAriaLabelledBy = input.getAttribute('aria-labelledby');
    const isHidden = input.getAttribute('type') === 'hidden';

    if (!isHidden && !hasLabel && !hasAriaLabel && !hasAriaLabelledBy) {
      issues.push({
        severity: 'critical',
        wcag: '1.3.1',
        description: 'Form input missing label',
        element: input.outerHTML.slice(0, 100),
        fix: 'Add label element, aria-label, or aria-labelledby',
      });
    }
  });

  // Check for proper heading hierarchy
  const headings = element.querySelectorAll('h1, h2, h3, h4, h5, h6');
  let lastLevel = 0;
  headings.forEach((heading) => {
    const level = parseInt(heading.tagName[1]);
    if (lastLevel > 0 && level > lastLevel + 1) {
      issues.push({
        severity: 'moderate',
        wcag: '1.3.1',
        description: `Heading level skipped (h${lastLevel} to h${level})`,
        element: heading.outerHTML.slice(0, 100),
        fix: 'Use sequential heading levels',
      });
    }
    lastLevel = level;
  });

  // Check for focus indicators (visual inspection required)
  // const focusables = element.querySelectorAll('button, a, input, select, textarea, [tabindex]');

  // Calculate score
  const criticalCount = issues.filter((i) => i.severity === 'critical').length;
  const seriousCount = issues.filter((i) => i.severity === 'serious').length;
  const moderateCount = issues.filter((i) => i.severity === 'moderate').length;
  const minorCount = issues.filter((i) => i.severity === 'minor').length;

  const score = Math.max(
    0,
    100 - (criticalCount * 20 + seriousCount * 10 + moderateCount * 5 + minorCount * 2)
  );

  return {
    component: componentName,
    issues,
    score,
  };
}
