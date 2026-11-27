from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['score', 'body']
        widgets = {
            'score': forms.NumberInput(attrs={'min': 1, 'max': 5, 'class': 'form-control'}),
            'body': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }

    def clean_score(self):
        score = self.cleaned_data['score']
        if score < 1 or score > 5:
            raise forms.ValidationError('Choose a rating from 1 to 5.')
        return score
