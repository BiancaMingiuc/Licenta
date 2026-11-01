/**
 * Application theme (Material Design 3, via react-native-paper).
 *
 * Beyond colours, this file carries one design decision that matters for
 * correctness rather than looks: the three detection outcomes get three
 * VISUALLY DISTINCT treatments.
 *
 * A security ALERT and a maintenance FAULT must never look the same. If a
 * broken camera produced the same red banner as an intruder, the user would
 * learn to dismiss both, and the alerting system would become useless -- the
 * exact failure mode decision D3 is meant to avoid. ALERT is therefore red
 * and loud; FAULT is amber and clearly "equipment, not people".
 *
 * Colour is never the ONLY carrier of meaning: each outcome also has an icon
 * and a text label, so the screens stay readable for colour-blind users and
 * in the grayscale screenshots that end up printed in the thesis.
 */

import { MD3DarkTheme, MD3LightTheme, type MD3Theme } from 'react-native-paper';

import type { DetectionOutcome, DetectionReason } from '../api/types';

/** Slate blue: reads as security tooling rather than consumer social app. */
const BRAND = {
  primaryLight: '#2B4C7E',
  primaryDark: '#9DB8E8',
};

export interface OutcomeStyle {
  /** Background for badges and banners. */
  container: string;
  /** Text/icon colour used on top of `container`. */
  onContainer: string;
  /** Saturated colour for borders and status dots. */
  accent: string;
  /** Material icon name. Meaning must survive without colour. */
  icon: string;
  /** Short human label shown next to the icon. */
  label: string;
}

export interface AppTheme extends MD3Theme {
  outcomes: Record<DetectionOutcome, OutcomeStyle>;
  spacing: (steps: number) => number;
  /** Maximum content width on a laptop browser, so lines stay readable. */
  maxContentWidth: number;
}

/** 8-point grid. Consistent rhythm is most of what makes a UI feel finished. */
const spacing = (steps: number): number => steps * 8;

const lightOutcomes: Record<DetectionOutcome, OutcomeStyle> = {
  KNOWN: {
    container: '#DCF3E4',
    onContainer: '#14532D',
    accent: '#1F8A4C',
    icon: 'check-circle',
    label: 'Expected',
  },
  ALERT: {
    container: '#FDE0DF',
    onContainer: '#7F1D1D',
    accent: '#D32F2F',
    icon: 'alert-octagon',
    label: 'Alert',
  },
  FAULT: {
    container: '#FDF0D5',
    onContainer: '#78350F',
    accent: '#C77700',
    icon: 'wrench',
    label: 'Fault',
  },
};

const darkOutcomes: Record<DetectionOutcome, OutcomeStyle> = {
  KNOWN: {
    container: '#17331F',
    onContainer: '#A7E8BE',
    accent: '#4ADE80',
    icon: 'check-circle',
    label: 'Expected',
  },
  ALERT: {
    container: '#3B1414',
    onContainer: '#FFB3AE',
    accent: '#FF6B61',
    icon: 'alert-octagon',
    label: 'Alert',
  },
  FAULT: {
    container: '#3A2A0D',
    onContainer: '#FFD79A',
    accent: '#FFB224',
    icon: 'wrench',
    label: 'Fault',
  },
};

export const lightTheme: AppTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: BRAND.primaryLight,
    background: '#F7F8FA',
    surface: '#FFFFFF',
    error: lightOutcomes.ALERT.accent,
  },
  outcomes: lightOutcomes,
  spacing,
  maxContentWidth: 880,
};

export const darkTheme: AppTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: BRAND.primaryDark,
    background: '#101317',
    surface: '#181C22',
    error: darkOutcomes.ALERT.accent,
  },
  outcomes: darkOutcomes,
  spacing,
  maxContentWidth: 880,
};

/**
 * Human-readable text for each journal reason.
 *
 * The backend stores the fine-grained reason, which is right for auditing but
 * wrong for a screen: `UNEXPECTED_ZONE` means nothing to a user. These
 * descriptions say what actually happened, in the user's terms.
 */
export const REASON_TEXT: Record<DetectionReason, { title: string; description: string }> = {
  KNOWN: {
    title: 'Expected person',
    description: 'Recognised, in a zone where they are expected.',
  },
  INTRUDER: {
    title: 'Unrecognised person',
    description: 'The face did not match anyone enrolled. A photo was kept.',
  },
  UNEXPECTED_ZONE: {
    title: 'Known person, unexpected zone',
    description: 'Recognised, but seen on a camera where they are not expected.',
  },
  EMPTY_WHITELIST: {
    title: 'Nobody enrolled yet',
    description: 'No face is enrolled, so every person detected is unknown.',
  },
  CAMERA_UNKNOWN: {
    title: 'Unregistered camera',
    description: 'A frame arrived from a camera that is not registered.',
  },
  CAMERA_DISABLED: {
    title: 'Disabled camera',
    description: 'This camera is turned off but is still sending frames.',
  },
  DEGRADED: {
    title: 'System could not evaluate',
    description: 'Detection failed. Surveillance may be incomplete.',
  },
};
