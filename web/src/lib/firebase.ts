import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyAtsf94mXEvkHgWanBdwZQIgm5oTUkcrn0",
  authDomain: "omnicrew-ai-2026.firebaseapp.com",
  projectId: "omnicrew-ai-2026",
  storageBucket: "omnicrew-ai-2026.firebasestorage.app",
  messagingSenderId: "157436451951",
  appId: "1:157436451951:web:1714a7f58af640488f419a",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
