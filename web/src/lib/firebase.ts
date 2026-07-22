/**
 * Firebase Web SDK v9 modular, initialised lazily and only in the browser.
 *
 * The config values below are the PUBLIC client identifiers. They are not
 * secrets and are safe in a client bundle; the service-account JSON in the
 * repo-root `.env` is a different thing entirely and never reaches this file.
 *
 * If the config is absent the app does not throw — `isConfigured()` returns
 * false and the data layer reads the bundled snapshot instead, so the site is
 * demonstrable without credentials.
 */
import { initializeApp, getApps, type FirebaseApp } from 'firebase/app';
import { getFirestore, type Firestore } from 'firebase/firestore';

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export function isConfigured(): boolean {
  if (process.env.NEXT_PUBLIC_FORCE_LOCAL_DATA === 'true') return false;
  return Boolean(config.apiKey && config.projectId);
}

export function projectId(): string | undefined {
  return config.projectId;
}

let app: FirebaseApp | null = null;
let db: Firestore | null = null;

export function firestore(): Firestore | null {
  if (!isConfigured()) return null;
  if (db) return db;
  app = getApps().length ? getApps()[0] : initializeApp(config as Record<string, string>);
  db = getFirestore(app);
  return db;
}
