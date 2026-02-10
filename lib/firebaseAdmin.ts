import { cert, getApps, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore } from "firebase-admin/firestore";

type AdminBundle = {
  auth: ReturnType<typeof getAuth>;
  db: ReturnType<typeof getFirestore>;
};

export function getAdmin(): AdminBundle {
  const serviceAccount = process.env.FIREBASE_SERVICE_ACCOUNT_KEY;
  if (!serviceAccount) {
    throw new Error("FIREBASE_SERVICE_ACCOUNT_KEY is not configured.");
  }

  if (!getApps().length) {
    initializeApp({
      credential: cert(JSON.parse(serviceAccount))
    });
  }

  return {
    auth: getAuth(),
    db: getFirestore()
  };
}
