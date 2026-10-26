import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors } from '../../components/ui';

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  return <Tabs screenOptions={{ tabBarActiveTintColor: colors.blue, tabBarInactiveTintColor: colors.muted, tabBarStyle: { borderTopColor: colors.line, backgroundColor: '#fff', height: 66 + Math.max(insets.bottom, 12), paddingTop: 10, paddingBottom: Math.max(insets.bottom, 12) }, tabBarLabelStyle: { fontSize: 12, fontWeight: '700' }, headerTintColor: colors.ink, headerStyle: { backgroundColor: colors.canvas }, headerShadowVisible: false }}>
    <Tabs.Screen name="index" options={{ title: 'Zephyr', tabBarLabel: 'Analyses', tabBarIcon: ({ color, size }) => <Ionicons name="grid-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="upload" options={{ title: 'New analysis', tabBarLabel: 'Upload', tabBarIcon: ({ color, size }) => <Ionicons name="cloud-upload-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="settings" options={{ title: 'Your account', tabBarLabel: 'Settings', tabBarIcon: ({ color, size }) => <Ionicons name="person-circle-outline" color={color} size={size} /> }} />
  </Tabs>;
}
