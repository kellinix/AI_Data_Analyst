import type { PropsWithChildren } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type KeyboardAvoidingViewProps, type TextInputProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

export const colors = { ink: '#29213F', muted: '#716B86', blue: '#7350D8', pale: '#F0EAFD', canvas: '#F8F5FC', line: '#E8E0F0', red: '#CC4256', green: '#0C8C76', teal: '#15B8A6', coral: '#F28B6B', gold: '#E5AE3E' };
export function Screen({ children, scroll = true, keyboardAvoidingBehavior, keyboardVerticalOffset = 0 }: PropsWithChildren<{ scroll?: boolean; keyboardAvoidingBehavior?: KeyboardAvoidingViewProps['behavior']; keyboardVerticalOffset?: number }>) {
  return <SafeAreaView style={styles.screen} edges={['left', 'right', 'bottom']}>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={keyboardAvoidingBehavior ?? (Platform.OS === 'ios' ? 'padding' : undefined)} keyboardVerticalOffset={keyboardVerticalOffset}>
      {scroll ? <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView> : children}
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
export function Heading({ title, subtitle }: { title: string; subtitle?: string }) {
  return <View style={{ gap: 8, marginBottom: 8 }}><Text style={styles.title}>{title}</Text>{subtitle && <Text style={styles.body}>{subtitle}</Text>}</View>;
}
export function Card({ children }: PropsWithChildren) { return <View style={styles.card}>{children}</View>; }
export function Label({ children }: PropsWithChildren) { return <Text style={styles.label}>{children}</Text>; }
export function Body({ children }: PropsWithChildren) { return <Text style={styles.body}>{children}</Text>; }
export function Button({ title, onPress, loading = false, disabled = false, variant = 'primary', icon }: {
  title: string; onPress: () => void; loading?: boolean; disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger'; icon?: React.ComponentProps<typeof Ionicons>['name'];
}) {
  const secondary = variant === 'secondary';
  return <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityState={{ disabled: disabled || loading, busy: loading }}
    disabled={disabled || loading} onPress={onPress} style={({ pressed }) => [styles.button, {
      backgroundColor: secondary ? colors.pale : variant === 'danger' ? colors.red : colors.blue,
      opacity: disabled || loading ? 0.55 : pressed ? 0.8 : 1,
    }]}>
    {loading ? <ActivityIndicator color={secondary ? colors.blue : '#fff'} /> : <>{icon && <Ionicons name={icon} size={18} color={secondary ? colors.blue : '#fff'} />}<Text style={[styles.buttonText, secondary && { color: colors.blue }]}>{title}</Text></>}
  </Pressable>;
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return <View style={{ gap: 7 }}><Text style={styles.label}>{label}</Text><TextInput accessibilityLabel={label} placeholderTextColor={colors.muted} style={[styles.input, props.multiline && { minHeight: 96, textAlignVertical: 'top' }]} {...props} /></View>;
}
export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <View accessibilityRole="alert" style={styles.error}><Text style={{ color: colors.red, lineHeight: 21 }}>{message}</Text>{retry && <Button title="Try again" variant="secondary" onPress={retry} />}</View>;
}
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <View style={{ padding: 32, gap: 14, alignItems: 'center' }}><ActivityIndicator color={colors.blue} /><Body>{label}</Body></View>;
}
export function Badge({ status }: { status: string }) {
  return <View style={{ alignSelf: 'flex-start', borderRadius: 20, backgroundColor: status === 'failed' ? '#FDECEF' : status === 'completed' ? '#DDF7F0' : colors.pale, paddingHorizontal: 11, paddingVertical: 6 }}>
    <Text style={{ color: status === 'failed' ? colors.red : status === 'completed' ? colors.green : colors.blue, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{status}</Text>
  </View>;
}
export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.canvas },
  content: { padding: 20, paddingBottom: 44, gap: 20, flexGrow: 1, maxWidth: 780, width: '100%', alignSelf: 'center' },
  title: { fontSize: 32, fontWeight: '800', color: colors.ink, letterSpacing: -1.1 },
  body: { color: colors.muted, fontSize: 15, lineHeight: 23 },
  label: { color: colors.ink, fontSize: 16, fontWeight: '700', letterSpacing: -0.2 },
  card: { padding: 20, borderRadius: 24, borderWidth: 1, borderColor: colors.line, backgroundColor: '#fff', gap: 14, shadowColor: '#4D2B76', shadowOpacity: 0.06, shadowRadius: 18, shadowOffset: { width: 0, height: 8 }, elevation: 2 },
  input: { backgroundColor: '#fff', borderColor: colors.line, borderWidth: 1.5, borderRadius: 15, minHeight: 52, padding: 14, color: colors.ink, fontSize: 16 },
  button: { minHeight: 52, borderRadius: 15, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 13 },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  error: { padding: 16, gap: 12, borderRadius: 12, backgroundColor: '#FFF0F1', borderWidth: 1, borderColor: '#F5CDD2' },
});
