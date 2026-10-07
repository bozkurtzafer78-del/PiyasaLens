import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js';
import { getAuth, onAuthStateChanged, signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut } from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js';
import { getFirestore, doc, getDoc, setDoc } from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js';

const app = initializeApp({
  apiKey: 'AIzaSyDCc1jjHOcd6U30JnvIrjEfiiQNxvWjYPk',
  authDomain: 'piyasalens.firebaseapp.com',
  projectId: 'piyasalens',
  storageBucket: 'piyasalens.firebasestorage.app',
  messagingSenderId: '870339844461',
  appId: '1:870339844461:web:b1bce7cd5a47abdd6c2264',
  measurementId: 'G-1QLL2547BM'
});
const auth = getAuth(app);
const db = getFirestore(app);
const profileRef = (uid) => doc(db, 'users', uid, 'profile', 'main');

export { auth, onAuthStateChanged, signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut, getDoc, setDoc, profileRef };
