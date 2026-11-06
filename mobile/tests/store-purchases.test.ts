import assert from 'node:assert/strict';
import test from 'node:test';
import { basePlanOffer, offerCopy, purchaseGuidance, subscriptionOfferToken } from '../src/lib/store-purchases';

const offers = [
  { id: 'trial', basePlanIdAndroid: 'monthly', displayPrice: 'Free', offerTokenAndroid: 'trial-token' },
  { id: 'monthly', basePlanIdAndroid: 'monthly', displayPrice: '£19.00', offerTokenAndroid: 'monthly-token' },
  { id: 'seven-days', basePlanIdAndroid: 'seven-days', displayPrice: '£5.99', offerTokenAndroid: 'weekly-token' },
];

test('the displayed Android base-plan price and requested offer token refer to the same plan', () => {
  assert.equal(basePlanOffer(offers, 'monthly').displayPrice, '£19.00');
  assert.equal(subscriptionOfferToken(offers, 'monthly'), 'monthly-token');
  assert.equal(subscriptionOfferToken(offers, 'seven-days'), 'weekly-token');
});

test('missing, ambiguous or tokenless base plans fail without choosing a promotional offer', () => {
  assert.throws(() => subscriptionOfferToken([offers[0]], 'monthly'));
  assert.throws(() => subscriptionOfferToken([...offers, offers[1]], 'monthly'));
  assert.throws(() => subscriptionOfferToken([{ ...offers[1], offerTokenAndroid: null }], 'monthly'));
});

test('one-time access and monthly renewal are distinguished before purchase', () => {
  assert.match(offerCopy('weekly').terms, /Does not renew/);
  assert.match(offerCopy('monthly').terms, /Renews monthly/);
});

test('pending or unavailable verification directs customers away from duplicate payment', () => {
  assert.match(purchaseGuidance('payment_pending'), /do not buy again/);
  assert.match(purchaseGuidance('verification_delayed'), /Restore purchases/);
  assert.match(purchaseGuidance('unknown_future_sdk_status'), /do not buy again/);
  assert.match(purchaseGuidance('owned_by_another_account'), /another Vesquiri account/);
});
