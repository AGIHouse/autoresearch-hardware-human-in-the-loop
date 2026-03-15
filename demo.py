#!/usr/bin/env python3
"""
Demonstration of the sparse-feedback research prototype.
Shows complete flow: cases -> feedback -> distilled rules -> retrieval -> scoring.
"""

import json
import argparse
from typing import Dict, List
from distill import load_feedback, load_cases, analyze_winning_patterns
from retrieve import retrieve_relevant_rules

def apply_rules_to_candidates(case: Dict, rules: Dict) -> Dict:
    """Apply retrieved rules to score candidates A and B without stacking duplicates."""
    candidate_a = case['candidate_a']
    candidate_b = case['candidate_b']
    
    scores = {'candidate_a': 0.0, 'candidate_b': 0.0}
    reasoning = {'candidate_a': [], 'candidate_b': []}
    
    # Group rules by type to avoid stacking similar evidence
    rule_groups = {
        'temporal_constraints': [r for r in rules['constraints'] if 'temporal' in r['type']],
        'spatial_constraints': [r for r in rules['constraints'] if 'spatial' in r['type']],
        'clutter_avoidance': [r for r in rules['anti_goals'] if 'clutter' in r['type']],
        'spatial_diffusion': [r for r in rules['anti_goals'] if 'diffusion' in r['type']]
    }
    
    # Apply best rule from each group, weighted by confidence
    for group_name, group_rules in rule_groups.items():
        if not group_rules:
            continue
        
        # Use the most confident rule from this group
        best_rule = max(group_rules, key=lambda r: r.get('confidence', 0.5))
        confidence_weight = best_rule.get('confidence', 0.5)
        
        if group_name == 'temporal_constraints':
            threshold = best_rule.get('threshold', 0.6)
            attr = 'temporal_consistency'
            
            for candidate_key, candidate in [('candidate_a', candidate_a), ('candidate_b', candidate_b)]:
                if attr in candidate:
                    base_score = 1.0 if candidate[attr] >= threshold else -0.5
                    weighted_score = base_score * confidence_weight
                    scores[candidate_key] += weighted_score
                    
                    status = "✓" if candidate[attr] >= threshold else "✗"
                    reasoning[candidate_key].append(
                        f"{status} Temporal consistency: {candidate[attr]:.2f} vs {threshold:.2f} "
                        f"(confidence: {confidence_weight:.2f}, score: {weighted_score:+.2f})"
                    )
        
        elif group_name == 'spatial_constraints':
            threshold = best_rule.get('threshold', 0.5)
            attr = 'spatial_compactness'
            
            for candidate_key, candidate in [('candidate_a', candidate_a), ('candidate_b', candidate_b)]:
                if attr in candidate:
                    base_score = 0.8 if candidate[attr] >= threshold else -0.3
                    weighted_score = base_score * confidence_weight
                    scores[candidate_key] += weighted_score
                    
                    status = "✓" if candidate[attr] >= threshold else "✗"
                    reasoning[candidate_key].append(
                        f"{status} Spatial compactness: {candidate[attr]:.2f} vs {threshold:.2f} "
                        f"(confidence: {confidence_weight:.2f}, score: {weighted_score:+.2f})"
                    )
        
        elif group_name == 'clutter_avoidance':
            max_threshold = best_rule.get('max_threshold', 0.6)
            attr = 'clutter_level'
            
            for candidate_key, candidate in [('candidate_a', candidate_a), ('candidate_b', candidate_b)]:
                if attr in candidate:
                    base_score = 0.6 if candidate[attr] <= max_threshold else -0.8
                    weighted_score = base_score * confidence_weight
                    scores[candidate_key] += weighted_score
                    
                    status = "✓" if candidate[attr] <= max_threshold else "✗"
                    reasoning[candidate_key].append(
                        f"{status} Clutter level: {candidate[attr]:.2f} vs {max_threshold:.2f} "
                        f"(confidence: {confidence_weight:.2f}, score: {weighted_score:+.2f})"
                    )
        
        elif group_name == 'spatial_diffusion':
            max_threshold = best_rule.get('max_threshold', 0.4)
            attr = 'spatial_compactness'
            
            for candidate_key, candidate in [('candidate_a', candidate_a), ('candidate_b', candidate_b)]:
                if attr in candidate:
                    base_score = 0.4 if candidate[attr] >= max_threshold else -0.6
                    weighted_score = base_score * confidence_weight
                    scores[candidate_key] += weighted_score
                    
                    status = "✓" if candidate[attr] >= max_threshold else "✗"
                    reasoning[candidate_key].append(
                        f"{status} Spatial diffusion check: {candidate[attr]:.2f} vs {max_threshold:.2f} "
                        f"(confidence: {confidence_weight:.2f}, score: {weighted_score:+.2f})"
                    )
    
    # Apply heuristics (soft preferences) - use best from each type
    heuristic_groups = {}
    for heuristic in rules['heuristics']:
        h_type = heuristic['type']
        if h_type not in heuristic_groups or heuristic.get('confidence', 0.5) > heuristic_groups[h_type].get('confidence', 0.5):
            heuristic_groups[h_type] = heuristic
    
    for heuristic in heuristic_groups.values():
        weight = heuristic.get('weight', 0.5)
        confidence = heuristic.get('confidence', 0.5)
        effective_weight = weight * confidence
        
        if heuristic['type'] == 'physical_plausibility':
            def plausibility_score(candidate):
                attrs = ['temporal_consistency', 'spatial_compactness', 'peak_strength']
                values = [candidate.get(attr, 0) for attr in attrs if attr in candidate]
                if values:
                    mean_val = sum(values) / len(values)
                    variance = sum((v - mean_val)**2 for v in values) / len(values)
                    return mean_val * effective_weight * (1 - variance)
                return 0
            
            plaus_a = plausibility_score(candidate_a)
            plaus_b = plausibility_score(candidate_b)
            
            scores['candidate_a'] += plaus_a
            scores['candidate_b'] += plaus_b
            
            reasoning['candidate_a'].append(f"Physical plausibility: +{plaus_a:.2f} (confidence: {confidence:.2f})")
            reasoning['candidate_b'].append(f"Physical plausibility: +{plaus_b:.2f} (confidence: {confidence:.2f})")
        
        elif heuristic['type'] == 'reliability_preference':
            def reliability_score(candidate):
                temp_cons = candidate.get('temporal_consistency', 0)
                clutter = candidate.get('clutter_level', 1)
                return (temp_cons * 0.7 + (1 - clutter) * 0.3) * effective_weight
            
            rel_a = reliability_score(candidate_a)
            rel_b = reliability_score(candidate_b)
            
            scores['candidate_a'] += rel_a
            scores['candidate_b'] += rel_b
            
            reasoning['candidate_a'].append(f"Reliability preference: +{rel_a:.2f} (confidence: {confidence:.2f})")
            reasoning['candidate_b'].append(f"Reliability preference: +{rel_b:.2f} (confidence: {confidence:.2f})")
    
    # Calculate true confidence based on rule quality and score separation
    total_rule_confidence = 0
    rule_count = 0
    for rule_group in rule_groups.values():
        if rule_group:
            total_rule_confidence += max(r.get('confidence', 0.5) for r in rule_group)
            rule_count += 1
    
    avg_rule_confidence = total_rule_confidence / max(rule_count, 1)
    score_separation = abs(scores['candidate_a'] - scores['candidate_b'])
    true_confidence = min(avg_rule_confidence * score_separation, 1.0)
    
    return {
        'scores': scores,
        'reasoning': reasoning,
        'winner': 'candidate_a' if scores['candidate_a'] > scores['candidate_b'] else 'candidate_b',
        'confidence': true_confidence,
        'avg_rule_confidence': avg_rule_confidence,
        'score_separation': score_separation
    }

def suggest_next_experiments(rules: Dict, cases: Dict) -> List[Dict]:
    """Suggest most informative next cases to evaluate."""
    suggestions = []
    
    # Find uncertain thresholds that need more evidence
    for constraint in rules['constraints']:
        if constraint.get('confidence', 0.5) < 0.7 or constraint.get('status') == 'uncertain':
            suggestions.append({
                'type': 'threshold_refinement',
                'priority': 'high',
                'description': f"Test {constraint['type']} threshold around {constraint['threshold']:.2f}",
                'rationale': f"Current rule has low confidence ({constraint.get('confidence', 0.5):.2f}) with {constraint.get('support_count', 1)} supporting cases",
                'suggested_case_attributes': {
                    constraint['type'].replace('_', ' '): [
                        constraint['threshold'] - 0.1,
                        constraint['threshold'] + 0.1
                    ]
                }
            })
    
    # Find contradictions that need resolution
    contradictions = rules.get('contradictions', [])
    contradiction_groups = {}
    for contradiction in contradictions:
        rule_type = contradiction['rule_type']
        if rule_type not in contradiction_groups:
            contradiction_groups[rule_type] = []
        contradiction_groups[rule_type].append(contradiction)
    
    for rule_type, rule_contradictions in contradiction_groups.items():
        suggestions.append({
            'type': 'contradiction_resolution',
            'priority': 'high',
            'description': f"Resolve {rule_type} contradictions",
            'rationale': f"Rule violated in {len(rule_contradictions)} winning cases: {', '.join(c['violating_case'] for c in rule_contradictions)}",
            'suggested_investigation': f"Examine why {rule_type} rule failed in these cases - may need context-dependent thresholds"
        })
    
    # Find attribute ranges with limited evidence
    discriminative_patterns = rules.get('discriminative_patterns', {})
    sparse_attributes = []
    for attr, patterns in discriminative_patterns.items():
        if len(patterns) <= 2:  # Limited evidence
            sparse_attributes.append((attr, len(patterns)))
    
    if sparse_attributes:
        sparse_attributes.sort(key=lambda x: x[1])  # Sort by evidence count
        attr, count = sparse_attributes[0]
        suggestions.append({
            'type': 'attribute_exploration',
            'priority': 'medium',
            'description': f"Gather more evidence on {attr} discrimination",
            'rationale': f"Only {count} discriminative examples for {attr} - need more cases to establish reliable patterns",
            'suggested_focus': f"Create cases with varying {attr} values while controlling other attributes"
        })
    
    # Find gaps in case coverage
    case_contexts = [case['context'] for case in cases.values()]
    context_types = set()
    for context in case_contexts:
        context_lower = context.lower()
        if 'urban' in context_lower:
            context_types.add('urban')
        elif 'highway' in context_lower or 'overpass' in context_lower:
            context_types.add('highway')
        elif 'airport' in context_lower:
            context_types.add('airport')
        elif 'border' in context_lower or 'desert' in context_lower:
            context_types.add('desert')
        elif 'maritime' in context_lower or 'coastal' in context_lower:
            context_types.add('maritime')
    
    missing_contexts = {'industrial', 'forest', 'mountain'} - context_types
    if missing_contexts:
        suggestions.append({
            'type': 'coverage_expansion',
            'priority': 'low',
            'description': f"Expand to {list(missing_contexts)} environments",
            'rationale': f"Current cases only cover: {', '.join(context_types)}. Missing contexts may have different discrimination patterns",
            'suggested_contexts': list(missing_contexts)
        })
    
    # Sort suggestions by priority
    priority_order = {'high': 3, 'medium': 2, 'low': 1}
    suggestions.sort(key=lambda x: priority_order.get(x['priority'], 1), reverse=True)
    
    return suggestions

def demonstrate_full_flow():
    """Run the complete sparse-feedback research demonstration."""
    print("🔬 SPARSE-FEEDBACK RESEARCH PROTOTYPE DEMONSTRATION")
    print("=" * 70)
    print()
    
    # Step 1: Load data
    print("📚 Step 1: Loading cases and feedback data...")
    cases = load_cases()
    feedback = load_feedback()
    print(f"   Loaded {len(cases)} cases and {len(feedback)} feedback items")
    print()
    
    # Step 2: Show example feedback
    print("💭 Step 2: Example expert feedback...")
    example_feedback = feedback[0]
    case_id = example_feedback['case_id']
    case = cases[case_id]
    
    print(f"   Case: {case_id} - {case['context']}")
    print(f"   Expert chose: {example_feedback['winner']}")
    print(f"   Reason: \"{example_feedback['reason']}\"")
    print()
    
    # Step 3: Distill rules from all feedback
    print("⚗️  Step 3: Distilling rules from expert feedback...")
    rules = analyze_winning_patterns(feedback, cases)
    
    summary = rules['extraction_summary']
    print(f"   Extracted {summary['constraints_extracted']} constraints, "
          f"{summary['anti_goals_extracted']} anti-goals, "
          f"{summary['heuristics_extracted']} heuristics")
    
    print("\n   Sample distilled rules:")
    if rules['constraints']:
        print(f"   🔒 Constraint: {rules['constraints'][0]['description']}")
    if rules['anti_goals']:
        print(f"   🚫 Anti-goal: {rules['anti_goals'][0]['description']}")
    if rules['heuristics']:
        print(f"   💡 Heuristic: {rules['heuristics'][0]['description']}")
    print()
    
    # Step 4: Choose a 'new' case for evaluation
    print("🆕 Step 4: Evaluating new case using distilled rules...")
    new_case_id = "sar_005"  # Case not in feedback training data
    new_case = cases[new_case_id]
    
    print(f"   New case: {new_case_id}")
    print(f"   Context: {new_case['context']}")
    print()
    
    print("   Candidate A attributes:")
    for attr, value in new_case['candidate_a'].items():
        if attr != 'summary':
            print(f"     {attr}: {value}")
    print(f"   Summary: {new_case['candidate_a']['summary']}")
    print()
    
    print("   Candidate B attributes:")
    for attr, value in new_case['candidate_b'].items():
        if attr != 'summary':
            print(f"     {attr}: {value}")
    print(f"   Summary: {new_case['candidate_b']['summary']}")
    print()
    
    # Step 5: Retrieve relevant rules
    print("🔍 Step 5: Retrieving relevant rules for this case...")
    retrieval_results = retrieve_relevant_rules(new_case_id, rules, cases, top_k=3)
    
    relevant_rules = {
        'constraints': [r for r in retrieval_results['retrieved_rules']['constraints'] if r['relevance_score'] > 0],
        'anti_goals': [r for r in retrieval_results['retrieved_rules']['anti_goals'] if r['relevance_score'] > 0],
        'heuristics': [r for r in retrieval_results['retrieved_rules']['heuristics'] if r['relevance_score'] > 0]
    }
    
    total_relevant = sum(len(relevant_rules[t]) for t in relevant_rules)
    print(f"   Found {total_relevant} relevant rules")
    
    for rule_type, display_name in [('constraints', 'Constraints'), ('anti_goals', 'Anti-goals'), ('heuristics', 'Heuristics')]:
        if relevant_rules[rule_type]:
            print(f"   {display_name}: {len(relevant_rules[rule_type])} relevant")
            for rule in relevant_rules[rule_type]:
                print(f"     • {rule['description']} (relevance: {rule['relevance_score']:.2f})")
    print()
    
    # Step 6: Score candidates using retrieved rules
    print("⚖️  Step 6: Scoring candidates using retrieved rules...")
    scoring_results = apply_rules_to_candidates(new_case, retrieval_results['retrieved_rules'])
    
    scores = scoring_results['scores']
    reasoning = scoring_results['reasoning']
    winner = scoring_results['winner']
    confidence = scoring_results['confidence']
    
    print(f"   Candidate A Score: {scores['candidate_a']:.2f}")
    for reason in reasoning['candidate_a']:
        print(f"     • {reason}")
    print()
    
    print(f"   Candidate B Score: {scores['candidate_b']:.2f}")
    for reason in reasoning['candidate_b']:
        print(f"     • {reason}")
    print()
    
    # Step 7: Final recommendation
    print("🏆 Step 7: Final recommendation...")
    print(f"   WINNER: {winner.upper()}")
    print(f"   Confidence: {confidence:.2f} (rule quality: {scoring_results['avg_rule_confidence']:.2f})")
    
    if winner == 'candidate_a':
        print(f"   Reasoning: Candidate A is recommended based on the distilled expert rules.")
    else:
        print(f"   Reasoning: Candidate B is recommended based on the distilled expert rules.")
    
    # Show which attributes were most decisive
    decisive_attrs = []
    for attr in ['temporal_consistency', 'spatial_compactness', 'clutter_level']:
        if attr in new_case['candidate_a'] and attr in new_case['candidate_b']:
            diff = abs(new_case['candidate_a'][attr] - new_case['candidate_b'][attr])
            if diff > 0.2:  # Significant difference
                decisive_attrs.append(attr)
    
    if decisive_attrs:
        print(f"   Key differentiating factors: {', '.join(decisive_attrs)}")
    print()
    
    # Step 8: Research assistant mode - suggest next experiments
    print("🔬 Step 8: Research assistant suggestions...")
    next_experiments = suggest_next_experiments(rules, cases)
    
    print(f"   Knowledge state analysis:")
    print(f"     • Rules extracted: {len(rules['constraints'])} constraints, {len(rules['anti_goals'])} anti-goals")
    print(f"     • Contradictions found: {len(rules.get('contradictions', []))}")
    print(f"     • Discriminative attributes: {len(rules.get('discriminative_patterns', {}))}")
    print()
    
    if next_experiments:
        print("   🎯 Recommended next experiments:")
        for i, exp in enumerate(next_experiments[:3], 1):  # Show top 3
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(exp['priority'], "⚪")
            print(f"     {i}. {priority_emoji} {exp['description']}")
            print(f"        Rationale: {exp['rationale']}")
            if 'suggested_investigation' in exp:
                print(f"        Investigation: {exp['suggested_investigation']}")
            print()
    else:
        print("   ✅ Knowledge base appears well-established - no immediate experiments needed")
        print()
    
    print("   📊 Evidence quality assessment:")
    well_supported = sum(1 for r in rules['constraints'] + rules['anti_goals'] if r.get('confidence', 0) >= 0.7)
    uncertain = sum(1 for r in rules['constraints'] + rules['anti_goals'] if r.get('confidence', 0) < 0.7)
    print(f"     • Well-supported rules: {well_supported}")
    print(f"     • Uncertain rules needing more evidence: {uncertain}")
    
    print()
    print("✅ Sparse-feedback research prototype demonstration complete!")
    print("   This system transforms sparse expert judgments into a reusable knowledge base")
    print("   that can evaluate future cases and guide research priorities.")

def main():
    """Main demonstration entry point."""
    parser = argparse.ArgumentParser(description="Demonstrate sparse-feedback research prototype")
    parser.add_argument("--case-id", help="Specific case ID to evaluate (default: sar_005)")
    
    args = parser.parse_args()
    
    if args.case_id:
        # Load data and run focused evaluation on specific case
        cases = load_cases()
        feedback = load_feedback()
        rules = analyze_winning_patterns(feedback, cases)
        
        print(f"Evaluating case {args.case_id} using distilled rules...")
        retrieval_results = retrieve_relevant_rules(args.case_id, rules, cases, top_k=5)
        scoring_results = apply_rules_to_candidates(cases[args.case_id], retrieval_results['retrieved_rules'])
        
        winner = scoring_results['winner']
        scores = scoring_results['scores']
        print(f"Winner: {winner} (A: {scores['candidate_a']:.2f}, B: {scores['candidate_b']:.2f})")
    else:
        # Run full demonstration
        demonstrate_full_flow()

if __name__ == "__main__":
    main()