import { Redirect } from 'expo-router';
import { useAuth } from '../providers/auth';

export default function Index() {
  const { session } = useAuth();
  return <Redirect href={session ? '/(tabs)' : '/sign-in'} />;
}
