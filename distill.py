#!/usr/bin/env python3
"""
Distillation engine for sparse-feedback research backend.
Extracts reusable constraints, anti-goals, and heuristics from human feedback.
"""

import json
import re
from collections import defaultdict
from typing import Dict, List, Set

def load_feedback(filepath: str = "feedback.json") -> List[Dict]:
    """Load human feedback from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data['feedback']

def load_cases(filepath: str = "cases.json") -> Dict[str, Dict]:
    """Load cases data for context."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return {case['case_id']: case for case in data['cases']}

def extract_keywords(text: str) -> Set[str]:
    """Extract relevant keywords from feedback text."""
    # Convert to lowercase and find relevant terms
    text = text.lower()
    
    # Define keyword patterns
    patterns = {
        'temporal': r'\b(temporal|time|tracking|persistence|coherence|stable|consistent)\w*',
        'spatial': r'\b(spatial|compact|diffuse|focus|localization|tight|spread)\w*',
        'clutter': r'\b(clutter|noise|contamina\w+|interferen\w+|clean)\w*',
        'strength': r'\b(strong|weak|bright|signal|peak|intensity)\w*',
        'plausible': r'\b(plausible|realistic|physical|believable|credible)\w*',
        'reliable': r'\b(reliable|trustworthy|dependable|consistent)\w*'
    }
    
    keywords = set()
    for category, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            keywords.add(category)
            keywords.update(matches)
    
    return keywords

def extract_discriminative_patterns(feedback_list: List[Dict], cases: Dict[str, Dict]) -> Dict:
    """Find attribute differences that actually discriminate between winners and losers."""
    discriminators = defaultdict(list)
    
    for feedback in feedback_list:
        case_id = feedback['case_id']
        winner_key = feedback['winner']
        loser_key = 'candidate_a' if winner_key == 'candidate_b' else 'candidate_b'
        
        case = cases[case_id]
        winner = case[winner_key]
        loser = case[loser_key]
        
        # Find significant attribute differences
        for attr in winner.keys():
            if attr in loser and isinstance(winner[attr], (int, float)):
                diff = winner[attr] - loser[attr]
                if abs(diff) > 0.1:  # Significant difference
                    discriminators[attr].append({
                        'diff': diff,
                        'winner_value': winner[attr],
                        'loser_value': loser[attr],
                        'case_id': case_id,
                        'reason': feedback['reason'],
                        'keywords': extract_keywords(feedback['reason'])
                    })
    
    return discriminators

def consolidate_rules(raw_rules: List[Dict], rule_type: str) -> List[Dict]:
    """Consolidate similar rules and track evidence."""
    consolidated = {}
    
    for rule in raw_rules:
        key = rule['type']
        if key not in consolidated:
            consolidated[key] = {
                'type': rule['type'],
                'description': rule['description'],
                'support_count': 1,
                'supporting_cases': [rule['source_case']],
                'evidence': [{'case': rule['source_case'], 'reason': rule.get('source_reason', '')}],
                'keywords': set(rule.get('keywords', [])),
                'values': []
            }
            
            # Copy type-specific fields
            if rule_type == 'constraints':
                consolidated[key]['threshold'] = rule['threshold']
                consolidated[key]['values'].append(rule['threshold'])
            elif rule_type == 'anti_goals':
                consolidated[key]['max_threshold'] = rule['max_threshold']
                consolidated[key]['values'].append(rule['max_threshold'])
            elif rule_type == 'heuristics':
                consolidated[key]['weight'] = rule['weight']
                consolidated[key]['values'].append(rule['weight'])
        else:
            # Merge with existing rule
            consolidated[key]['support_count'] += 1
            consolidated[key]['supporting_cases'].append(rule['source_case'])
            consolidated[key]['evidence'].append({'case': rule['source_case'], 'reason': rule.get('source_reason', '')})
            consolidated[key]['keywords'].update(rule.get('keywords', []))
            
            # Update thresholds/weights based on new evidence
            if rule_type == 'constraints':
                consolidated[key]['values'].append(rule['threshold'])
                consolidated[key]['threshold'] = sum(consolidated[key]['values']) / len(consolidated[key]['values'])
            elif rule_type == 'anti_goals':
                consolidated[key]['values'].append(rule['max_threshold'])
                consolidated[key]['max_threshold'] = sum(consolidated[key]['values']) / len(consolidated[key]['values'])
            elif rule_type == 'heuristics':
                consolidated[key]['values'].append(rule['weight'])
                consolidated[key]['weight'] = sum(consolidated[key]['values']) / len(consolidated[key]['values'])
    
    # Convert back to list and add confidence scores
    result = []
    for rule in consolidated.values():
        rule['keywords'] = list(rule['keywords'])
        rule['confidence'] = min(rule['support_count'] / 3.0, 1.0)  # Higher confidence with more support
        rule['status'] = 'well_supported' if rule['support_count'] >= 2 else 'proposed'
        del rule['values']  # Clean up temporary field
        result.append(rule)
    
    return result

def analyze_winning_patterns(feedback_list: List[Dict], cases: Dict[str, Dict]) -> Dict:
    """Analyze patterns in winning candidates to extract rules with deduplication."""
    raw_constraints = []
    raw_anti_goals = []
    raw_heuristics = []
    
    # First, extract discriminative patterns
    discriminators = extract_discriminative_patterns(feedback_list, cases)
    
    # Track which attributes correlate with wins
    winning_attributes = defaultdict(list)
    
    for feedback in feedback_list:
        case_id = feedback['case_id']
        winner = feedback['winner'] 
        reason = feedback['reason']
        keywords = extract_keywords(reason)
        
        # Get the winning candidate's attributes
        case = cases[case_id]
        winning_candidate = case[winner]
        
        # Store winning attributes
        for attr, value in winning_candidate.items():
            if isinstance(value, (int, float)):
                winning_attributes[attr].append(value)
        
        # Extract constraints using discriminative analysis
        if any(word in keywords for word in ['temporal', 'consistent', 'tracking']):
            # Use actual winning threshold if available
            threshold = 0.6
            if 'temporal_consistency' in discriminators:
                avg_winner_value = sum(d['winner_value'] for d in discriminators['temporal_consistency']) / len(discriminators['temporal_consistency'])
                threshold = max(0.5, avg_winner_value - 0.1)  # Slightly below average winner
            
            raw_constraints.append({
                "type": "temporal_consistency",
                "description": "Target must maintain temporal consistency for reliable tracking",
                "threshold": threshold,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'temporal', 'consistent', 'tracking', 'persistence'})
            })
        
        if any(word in keywords for word in ['compact', 'spatial']):
            threshold = 0.5
            if 'spatial_compactness' in discriminators:
                avg_winner_value = sum(d['winner_value'] for d in discriminators['spatial_compactness']) / len(discriminators['spatial_compactness'])
                threshold = max(0.4, avg_winner_value - 0.1)
            
            raw_constraints.append({
                "type": "spatial_compactness", 
                "description": "Target should maintain spatial compactness for precise localization",
                "threshold": threshold,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'compact', 'spatial', 'tight', 'focus'})
            })
        
        # Extract anti-goals using discriminative analysis
        if any(word in keywords for word in ['clutter', 'contamina', 'noise']):
            max_threshold = 0.6
            if 'clutter_level' in discriminators:
                avg_loser_value = sum(d['loser_value'] for d in discriminators['clutter_level'] if d['diff'] < 0) / max(1, len([d for d in discriminators['clutter_level'] if d['diff'] < 0]))
                max_threshold = min(0.7, avg_loser_value + 0.1)  # Slightly above average loser
            
            raw_anti_goals.append({
                "type": "clutter_avoidance",
                "description": "Avoid interpretations with high clutter contamination",
                "max_threshold": max_threshold,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'clutter', 'contamination', 'noise', 'interference'})
            })
        
        if any(word in keywords for word in ['diffuse', 'spread']):
            max_threshold = 0.4
            if 'spatial_compactness' in discriminators:
                # Diffusion is inverse of compactness
                avg_loser_compactness = sum(d['loser_value'] for d in discriminators['spatial_compactness'] if d['diff'] > 0) / max(1, len([d for d in discriminators['spatial_compactness'] if d['diff'] > 0]))
                max_threshold = min(0.5, avg_loser_compactness + 0.1)
            
            raw_anti_goals.append({
                "type": "spatial_diffusion", 
                "description": "Avoid overly diffuse spatial signatures",
                "max_threshold": max_threshold,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'diffuse', 'spread', 'weak'})
            })
        
        # Extract heuristics (preference rules)
        if any(word in keywords for word in ['plausible', 'physical', 'realistic']):
            raw_heuristics.append({
                "type": "physical_plausibility",
                "description": "Prefer physically plausible interpretations",
                "weight": 0.8,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'plausible', 'physical', 'realistic', 'believable'})
            })
        
        if any(word in keywords for word in ['reliable', 'dependable']):
            raw_heuristics.append({
                "type": "reliability_preference",
                "description": "Prefer reliable and consistent detections",
                "weight": 0.7,
                "source_case": case_id,
                "source_reason": reason,
                "keywords": list(keywords & {'reliable', 'dependable', 'trustworthy'})
            })
    
    # Consolidate rules to eliminate duplicates
    constraints = consolidate_rules(raw_constraints, 'constraints')
    anti_goals = consolidate_rules(raw_anti_goals, 'anti_goals')
    heuristics = consolidate_rules(raw_heuristics, 'heuristics')
    
    # Calculate average thresholds from winning patterns
    avg_attributes = {}
    for attr, values in winning_attributes.items():
        if values and isinstance(values[0], (int, float)):
            avg_attributes[attr] = sum(values) / len(values)
    
    # Check for contradictions and adjust rule confidence
    contradictions = detect_contradictions(constraints, anti_goals, feedback_list, cases)
    
    # Adjust rule confidence based on contradictions
    for rule in constraints + anti_goals:
        rule_contradictions = [c for c in contradictions if c['rule_type'] == rule['type']]
        if rule_contradictions:
            penalty = min(0.3 * len(rule_contradictions), 0.7)  # Max 70% penalty
            rule['confidence'] = max(0.1, rule['confidence'] - penalty)
            rule['status'] = 'contradicted' if rule['confidence'] < 0.3 else 'uncertain'
            rule['contradictions'] = len(rule_contradictions)
    
    return {
        "constraints": constraints,
        "anti_goals": anti_goals, 
        "heuristics": heuristics,
        "winning_patterns": avg_attributes,
        "discriminative_patterns": dict(discriminators),
        "contradictions": contradictions,
        "extraction_summary": {
            "total_feedback_items": len(feedback_list),
            "constraints_extracted": len(constraints),
            "anti_goals_extracted": len(anti_goals),
            "heuristics_extracted": len(heuristics),
            "discriminative_attributes": len(discriminators),
            "contradictions_found": len(contradictions)
        }
    }

def detect_contradictions(constraints: List[Dict], anti_goals: List[Dict], 
                         feedback_list: List[Dict], cases: Dict[str, Dict]) -> List[Dict]:
    """Find cases where rules are violated by winning candidates."""
    contradictions = []
    
    for feedback in feedback_list:
        case_id = feedback['case_id']
        winner_key = feedback['winner']
        winner = cases[case_id][winner_key]
        
        # Check constraint violations in winners
        for constraint in constraints:
            if constraint['type'] == 'temporal_consistency':
                attr = 'temporal_consistency'
                threshold = constraint['threshold']
                if attr in winner and winner[attr] < threshold:
                    contradictions.append({
                        'rule_type': constraint['type'],
                        'rule_description': constraint['description'],
                        'violating_case': case_id,
                        'violation_value': winner[attr],
                        'threshold': threshold,
                        'reason': feedback['reason'],
                        'severity': (threshold - winner[attr]) / threshold
                    })
            
            elif constraint['type'] == 'spatial_compactness':
                attr = 'spatial_compactness'
                threshold = constraint['threshold']
                if attr in winner and winner[attr] < threshold:
                    contradictions.append({
                        'rule_type': constraint['type'],
                        'rule_description': constraint['description'],
                        'violating_case': case_id,
                        'violation_value': winner[attr],
                        'threshold': threshold,
                        'reason': feedback['reason'],
                        'severity': (threshold - winner[attr]) / threshold
                    })
        
        # Check anti-goal violations in winners
        for anti_goal in anti_goals:
            if anti_goal['type'] == 'clutter_avoidance':
                attr = 'clutter_level'
                max_threshold = anti_goal['max_threshold']
                if attr in winner and winner[attr] > max_threshold:
                    contradictions.append({
                        'rule_type': anti_goal['type'],
                        'rule_description': anti_goal['description'],
                        'violating_case': case_id,
                        'violation_value': winner[attr],
                        'threshold': max_threshold,
                        'reason': feedback['reason'],
                        'severity': (winner[attr] - max_threshold) / (1.0 - max_threshold)
                    })
            
            elif anti_goal['type'] == 'spatial_diffusion':
                attr = 'spatial_compactness'
                max_threshold = anti_goal['max_threshold']
                if attr in winner and winner[attr] < max_threshold:
                    contradictions.append({
                        'rule_type': anti_goal['type'],
                        'rule_description': anti_goal['description'],
                        'violating_case': case_id,
                        'violation_value': winner[attr],
                        'threshold': max_threshold,
                        'reason': feedback['reason'],
                        'severity': (max_threshold - winner[attr]) / max_threshold
                    })
    
    return contradictions

def save_rules(rules: Dict, filepath: str = "rules.json"):
    """Save distilled rules to JSON file."""
    with open(filepath, 'w') as f:
        json.dump(rules, f, indent=2)

def print_summary(rules: Dict):
    """Print a readable summary of extracted rules."""
    print("🔍 SPARSE FEEDBACK DISTILLATION RESULTS")
    print("=" * 50)
    
    summary = rules['extraction_summary']
    print(f"📊 Processed {summary['total_feedback_items']} feedback items")
    print(f"📋 Extracted {summary['constraints_extracted']} constraints")
    print(f"🚫 Extracted {summary['anti_goals_extracted']} anti-goals") 
    print(f"💡 Extracted {summary['heuristics_extracted']} heuristics")
    print()
    
    print("🔒 CONSTRAINTS (Hard Requirements):")
    for i, constraint in enumerate(rules['constraints'], 1):
        print(f"  {i}. {constraint['description']}")
        print(f"     Type: {constraint['type']}, Threshold: {constraint.get('threshold', 'N/A')}")
        print(f"     Source: {constraint['source_case']}")
        print()
    
    print("🚫 ANTI-GOALS (Things to Avoid):")
    for i, anti_goal in enumerate(rules['anti_goals'], 1):
        print(f"  {i}. {anti_goal['description']}")
        print(f"     Type: {anti_goal['type']}, Max Threshold: {anti_goal.get('max_threshold', 'N/A')}")
        print(f"     Source: {anti_goal['source_case']}")
        print()
    
    print("💡 HEURISTICS (Preference Rules):")
    for i, heuristic in enumerate(rules['heuristics'], 1):
        print(f"  {i}. {heuristic['description']}")
        print(f"     Type: {heuristic['type']}, Weight: {heuristic.get('weight', 'N/A')}")
        print(f"     Source: {heuristic['source_case']}")
        print()
    
    print("📈 WINNING PATTERNS (Average Attributes):")
    for attr, avg_value in rules['winning_patterns'].items():
        if attr != 'summary':  # Skip summary field
            print(f"  {attr}: {avg_value:.2f}")
    print()

def main():
    """Main distillation workflow."""
    print("Starting feedback distillation...")
    
    # Load data
    feedback = load_feedback()
    cases = load_cases()
    
    print(f"Loaded {len(feedback)} feedback items and {len(cases)} cases")
    
    # Extract rules
    rules = analyze_winning_patterns(feedback, cases)
    
    # Save rules
    save_rules(rules)
    print(f"Saved distilled rules to rules.json")
    
    # Print summary
    print_summary(rules)

if __name__ == "__main__":
    main()